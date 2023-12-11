from __future__ import annotations

import json
import logging
import sys
import textwrap
import typing
import zoneinfo
from contextlib import closing
from functools import cache
from pathlib import Path
from typing import Annotated

import click
import croniter
import mistune
import pydantic
import ruamel.yaml

import cron_times.db
import cron_times.logging

if typing.TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any, Literal

    from pydantic_core.core_schema import (
        SerializerFunctionWrapHandler,
        ValidatorFunctionWrapHandler,
    )

    FieldName = Literal[
        "name",
        "schedule",
        "timezone",
        "description",
        "labels",
        "metadata",
        "enabled",
    ]


logger = logging.getLogger(__name__)
markdown = mistune.create_markdown(
    hard_wrap=True,
    plugins=["strikethrough", "footnotes", "table", "url", "task_lists"],
)


def _wrap_validate_timezone(v: Any, validator: ValidatorFunctionWrapHandler) -> Any:
    if isinstance(v, str):
        try:
            v = zoneinfo.ZoneInfo(v)
        except zoneinfo.ZoneInfoNotFoundError:
            raise AssertionError(f'Invalid timezone "{v}"') from None
    return validator(v)


def _serialize_timezone(
    tz: zoneinfo.ZoneInfo, serializer: SerializerFunctionWrapHandler
) -> str:
    return tz.key


def _validate_cron_expr(v: str) -> str:
    try:
        croniter.croniter(v)
    except ValueError:
        raise AssertionError(f"Invalid cron expression {v}") from None
    return v


def _wrap_validate_json(v: Any, validator: ValidatorFunctionWrapHandler) -> Any:
    if isinstance(v, str):
        v = json.loads(v)
    return validator(v)


def _serialize_json(v: Any) -> str:
    return json.dumps(v)


class Job(pydantic.BaseModel):
    """Job definition to be read from taskfile."""

    group: str | None = None
    """Key for job group."""
    raw_key: str | None = pydantic.Field(default=None, alias="key")
    """Key for job."""

    name: str
    """Name of job."""
    schedule: Annotated[str, pydantic.AfterValidator(_validate_cron_expr)]
    """Cron expression."""
    timezone: Annotated[
        pydantic.InstanceOf[zoneinfo.ZoneInfo],
        pydantic.WrapValidator(_wrap_validate_timezone),
        pydantic.WrapSerializer(_serialize_timezone),
    ] = pydantic.Field(zoneinfo.ZoneInfo("UTC"))
    """Timezone."""
    raw_description: str | None = pydantic.Field(default=None, alias="description")
    """Description of job."""
    labels: Annotated[
        list[str],
        pydantic.WrapValidator(_wrap_validate_json),
        pydantic.PlainSerializer(_serialize_json),
    ] = pydantic.Field(default_factory=list)
    """Labels of job."""
    metadata: Annotated[
        dict[str, pydantic.JsonValue],
        pydantic.WrapValidator(_wrap_validate_json),
        pydantic.PlainSerializer(_serialize_json),
    ] = pydantic.Field(default_factory=dict)
    """Metadata of job."""
    enabled: bool = True
    """Whether job is enabled."""
    description_is_html: bool = False
    """Whether description is HTML."""

    @pydantic.computed_field
    @property
    def key(self) -> str:
        """Key for job. It uses inputted "key" if specified, otherwise "name"."""
        return self.raw_key or self.name

    @pydantic.computed_field
    @property
    def description(self) -> str:
        """Rendered HTML job description."""
        raw = self.raw_description or ""
        if self.description_is_html:
            return raw
        return markdown(raw)

    def delete(self) -> bool:
        """Delete this job from database."""
        logger.debug("Delete job %s from database", self.key)

        db = cron_times.db.get_db()
        with closing(db.cursor()) as cur:
            cur.execute(
                """
                DELETE FROM job
                WHERE "group" = :group AND key = :key
                """,
                {"group": self.group, "key": self.key},
            )
            db.commit()

        return cur.rowcount > 0

    @classmethod
    def objects_iter(cls, *, group: str | None = None) -> Iterator[Job]:
        """Get jobs."""
        logger.debug("Get jobs from database")

        query = textwrap.dedent(
            """
            SELECT
                "group", key, name, schedule, timezone, description, labels, metadata, enabled
            FROM job
            """
        )
        data = {}

        if group:
            query += 'WHERE "group" = :group'
            data["group"] = group

        logger.debug("Query= %s", query)
        logger.debug("Data= %r", data)

        db = cron_times.db.get_db()
        with closing(db.cursor()) as cur:
            cur.execute(query, data)
            for (
                group,
                key,
                name,
                schedule,
                timezone,
                description,
                labels,
                metadata,
                enabled,
            ) in cur:
                yield cls(
                    group=group,
                    key=key,
                    name=name,
                    schedule=schedule,
                    timezone=timezone,
                    description=description,
                    labels=labels,
                    metadata=metadata,
                    enabled=enabled,
                    description_is_html=True,
                )

    @classmethod
    def objects_upsert(cls, jobs: list[Job], update_fields: list[FieldName]) -> int:
        """Save this job to database."""
        query = get_job_insert_command(tuple(update_fields))
        logger.debug("Save jobs to database")
        logger.debug(f"Query= {query}")

        data = [
            job.model_dump(
                include={
                    "group",
                    "key",
                    "name",
                    "schedule",
                    "timezone",
                    "description",
                    "labels",
                    "metadata",
                    "enabled",
                }
            )
            for job in jobs
        ]
        logger.debug(f"Data= {data!r}")

        db = cron_times.db.get_db()
        with closing(db.cursor()) as cur:
            cur.executemany(query, data)
            db.commit()

        return cur.rowcount

    @classmethod
    def objects_sync(
        cls,
        *,
        group: str,
        jobs: list[Job],
        update_fields: list[FieldName],
        missing: Literal["ignore", "inactive", "remove"],
    ):
        """Sync jobs in database with the given job list."""
        # prepare jobs to save
        jobs_to_save = {}
        for job in jobs:
            jobs_to_save[job.key] = job.model_copy(
                update={
                    "group": group,
                    "description_is_html": False,
                }
            )

        # get existing jobs from database
        existing_jobs = {job.key: job for job in cls.objects_iter(group=group)}

        # remove jobs that are missing from taskfile
        missing_jobs = set(existing_jobs) - set(jobs_to_save)

        for key in missing_jobs:
            if missing == "ignore":
                continue
            elif missing == "inactive":
                logger.debug("Set job '%s' to inactive", key)
                jobs_to_save[key] = existing_jobs[key].model_copy(
                    update={"enabled": False}
                )
                update_fields = set(update_fields) | {"enabled"}
            elif missing == "remove":
                existing_jobs[key].delete()

        # update jobs that are in taskfile
        n = Job.objects_upsert(
            jobs_to_save.values(),
            update_fields=update_fields,
        )
        logger.info(f"Update {n} jobs for {group}")


@cache
def get_job_insert_command(update_fields: tuple[FieldName, ...]) -> str:
    query = textwrap.dedent(
        """
        INSERT INTO job (
            "group", key, name, schedule, timezone, description, labels,
            metadata, enabled
        )
        VALUES
        (
            :group, :key, :name, :schedule, :timezone, :description, :labels,
            :metadata, :enabled
        )
        """
    )

    update_field_command = []
    for field in update_fields:
        update_field_command.append(f"{field} = EXCLUDED.{field}")

    if update_field_command:
        query += 'ON CONFLICT ("group", key) DO UPDATE SET ' + ",\n  ".join(
            update_field_command
        )

    return query


class TaskFile(pydantic.BaseModel):
    """Task file definition."""

    group: str | None = None
    """Group name for internal use."""
    jobs: list[Job] = pydantic.Field(default_factory=list)
    """List of jobs."""


@click.command()
@click.argument("file", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-m",
    "--missing",
    type=click.Choice(["ignore", "inactive", "remove"]),
    default="remove",
    show_default=True,
    help="Action to take when a job is missing from the taskfile. "
    "'ignore' will do nothing. "
    "'inactive' will set the job to inactive. "
    "'remove' will remove the job from the database.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING"]),
    default="INFO",
    help="Set log level.",
)
def read_file(file: list[Path], missing: str, log_level: int):
    """Load taskfile into database."""
    cron_times.logging.setup_logging(log_level)

    yaml = ruamel.yaml.YAML(typ="safe")

    for path in file:
        logger.info("Loading %s", path)

        with path.open() as fd:
            raw_config = yaml.load(fd)

        try:
            config = TaskFile.model_validate(raw_config)
        except pydantic.ValidationError as e:
            logger.error(f"Failed to parse {path}: {e}")
            sys.exit(1)

        group_name = config.group or f"file-{path.stem}"

        logger.info("Found %d jobs in %s", len(config.jobs), path)

        Job.objects_sync(
            group=group_name,
            jobs=config.jobs,
            update_fields=(
                "name",
                "schedule",
                "timezone",
                "description",
                "labels",
                "metadata",
                "enabled",
            ),
            missing=missing,
        )

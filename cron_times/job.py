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
import flask.logging
import mistune
import pydantic
import ruamel.yaml

import cron_times.db

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

    @classmethod
    def query(cls) -> Iterator[Job]:
        """Get jobs."""
        db = cron_times.db.get_db()
        with closing(db.cursor()) as cur:
            cur.execute(
                """
                SELECT
                    name, schedule, timezone, description, labels, metadata, enabled
                FROM job
                """
            )
            for (
                name,
                schedule,
                timezone,
                description,
                labels,
                metadata,
                enabled,
            ) in cur:
                yield cls(
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
    def upsert(cls, jobs: list[Job], update_fields: list[FieldName]) -> int:
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


class TaskFile(pydantic.BaseModel):
    """Task file definition."""

    group: str | None = None
    """Group name for internal use."""
    jobs: list[Job] = pydantic.Field(default_factory=list)
    """List of jobs."""


@click.command()
@click.argument("file", nargs=-1, type=click.Path(exists=True, path_type=Path))
def read_file(file: list[Path]):
    """Load taskfile into database."""
    logger.addHandler(flask.logging.default_handler)
    logger.setLevel(logging.INFO)

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
        jobs_to_save = []
        for orig_job in config.jobs:
            jobs_to_save.append(
                orig_job.model_copy(
                    update={
                        "group": group_name,
                        "description_is_html": False,
                    }
                )
            )

        n = Job.upsert(
            jobs_to_save,
            update_fields=(
                "name",
                "schedule",
                "timezone",
                "description",
                "labels",
                "metadata",
                "enabled",
            ),
        )
        logger.info(f"Loaded {n} jobs from {path}")


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

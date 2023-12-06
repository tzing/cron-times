from __future__ import annotations

import json
import logging
import sys
import typing
import zoneinfo
from contextlib import closing
from pathlib import Path
from typing import Annotated

import click
import croniter
import flask.logging
import markupsafe
import mistune
import pydantic
import ruamel.yaml

import cron_times.db

if typing.TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from pydantic_core.core_schema import (
        SerializerFunctionWrapHandler,
        ValidatorFunctionWrapHandler,
    )

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
    group: str | None = None
    """Key for job group."""
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
    description: str | None = None
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
    use_markdown: bool = True
    """Whether to render description from markdown to HTML."""

    @pydantic.computed_field
    @property
    def description_rendered(self) -> str:
        raw = self.description or ""
        if self.use_markdown:
            return markdown(raw)
        return markupsafe.escape(raw).replace("\n", markupsafe.Markup("<br>"))


def get_jobs() -> Iterator[Job]:
    db = cron_times.db.get_db()
    with closing(db.cursor()) as cur:
        cur.execute(
            """
            SELECT
                "group",
                name,
                schedule,
                timezone,
                description,
                labels,
                metadata,
                enabled,
                use_markdown
            FROM job
            """
        )
        for (
            group,
            name,
            schedule,
            timezone,
            description,
            labels,
            metadata,
            enabled,
            use_markdown,
        ) in cur:
            yield Job(
                group=group,
                name=name,
                schedule=schedule,
                timezone=timezone,
                description=description,
                labels=labels,
                metadata=metadata,
                enabled=enabled,
                use_markdown=use_markdown,
            )


class TaskFile(pydantic.BaseModel):
    jobs: list[Job] = pydantic.Field(default_factory=list)


def save_jobs(group_name: str | None, jobs: list[Job]) -> int:
    db = cron_times.db.get_db()

    # delete existing jobs
    if group_name:
        with closing(db.cursor()) as cur:
            cur.execute(
                """
                DELETE FROM job
                WHERE "group" = :group
                """,
                {"group": group_name},
            )
            logger.info(f"Deleted {cur.rowcount} existing {group_name} job(s)")
            db.commit()

    # update group field
    if group_name:
        updated_jobs = []
        for job in jobs:
            updated_jobs.append(job.model_copy(update={"group": group_name}))
        jobs = updated_jobs

    # save to database
    with closing(db.cursor()) as cur:
        cur.executemany(
            """
            INSERT INTO job (
                "group",
                name,
                schedule,
                timezone,
                description,
                labels,
                metadata,
                enabled,
                use_markdown
            )
            VALUES (
                :group,
                :name,
                :schedule,
                :timezone,
                :description,
                :labels,
                :metadata,
                :enabled,
                :use_markdown
            )
            """,
            (job.model_dump() for job in jobs),
        )
        db.commit()

    return cur.rowcount


@click.command()
@click.argument("taskfile", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("-g", "--group", help="group name")
@click.option(
    "-m",
    "--mode",
    type=click.Choice(["replace", "append"], False),
    default="replace",
    help="Insert mode; "
    "'replace' to delete all jobs with the same group and insert new ones, "
    "'append' to insert new jobs without deleting existing ones.",
)
def load_taskfile(taskfile: list[Path], group: str | None, mode: str):
    """Load taskfile into database."""
    logger.addHandler(flask.logging.default_handler)
    logger.setLevel(logging.INFO)

    if mode == "replace" and group is None:
        raise click.BadParameter(
            "Group must be specified in replace mode. "
            "Use --mode=append to insert jobs in append mode."
        )

    yaml = ruamel.yaml.YAML(typ="safe")

    for path in taskfile:
        logger.debug(f"Start reading {path}")

        with path.open() as fd:
            raw_config = yaml.load(fd)

        try:
            f = TaskFile.model_validate(raw_config)
        except pydantic.ValidationError as e:
            logger.error(f"Failed to load {path}: {e}")
            sys.exit(1)

        save_jobs(
            group_name=group if mode == "replace" else None,
            jobs=f.jobs,
        )

        logger.info(f"Loaded {len(f.jobs)} jobs from {path}")

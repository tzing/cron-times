from __future__ import annotations

import json
import logging
import sqlite3
import textwrap
import typing
import zoneinfo
from contextlib import closing
from typing import Annotated

import click
import flask
import markupsafe
import mistune
import pydantic

import cron_times.logging

if typing.TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from pydantic_core.core_schema import ValidatorFunctionWrapHandler

logger = logging.getLogger(__name__)
markdown = mistune.create_markdown(
    hard_wrap=True,
    plugins=["strikethrough", "footnotes", "table", "url", "task_lists"],
)


def get_db() -> sqlite3.Connection:
    if "db" not in flask.g:
        sqlite3.paramstyle = "named"
        flask.g.db = sqlite3.connect(
            flask.current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )

    return flask.g.db


def close_db(e=None) -> None:
    db = flask.g.pop("db", None)
    if db is not None:
        db.close()


def _wrap_validate_timezone(v: Any, validator: ValidatorFunctionWrapHandler) -> Any:
    if isinstance(v, str):
        try:
            v = zoneinfo.ZoneInfo(v)
        except zoneinfo.ZoneInfoNotFoundError:
            raise AssertionError(f'Invalid timezone "{v}"') from None
    return validator(v)


def _wrap_validate_json(v: Any, validator: ValidatorFunctionWrapHandler) -> Any:
    if isinstance(v, str):
        v = json.loads(v)
    return validator(v)


class Job(pydantic.BaseModel):
    """Job definition."""

    key: str
    """Unique key (within the group) for the job."""

    name: str
    """Name of the job."""

    schedule: str
    """Schedule in cron expression."""

    timezone: Annotated[
        pydantic.InstanceOf[zoneinfo.ZoneInfo],
        pydantic.WrapValidator(_wrap_validate_timezone),
    ]
    """Timezone for the schedule."""

    raw_description: str | None = pydantic.Field(default=None, alias="description")
    """Description of the job."""

    labels: Annotated[
        list[str],
        pydantic.WrapValidator(_wrap_validate_json),
    ] = pydantic.Field(default_factory=list)
    """Labels for the job."""

    raw_metadata: Annotated[
        dict[str, pydantic.JsonValue],
        pydantic.WrapValidator(_wrap_validate_json),
    ] = pydantic.Field(default_factory=dict, alias="metadata")
    """Metadata for the job."""

    enabled: bool = True
    """Whether the job is enabled."""

    @pydantic.computed_field
    @property
    def description(self) -> str:
        """Rendered HTML job description."""
        raw = self.raw_description or ""
        raw = textwrap.dedent(raw)
        return markdown(raw)

    @pydantic.computed_field
    @property
    def metadata(self) -> dict[str, str]:
        """Rendered HTML for metadata."""
        output = {}
        for key, value in self.raw_metadata.items():
            value = markupsafe.escape(value)
            if value.startswith(("http://", "https://")):
                value = f'<a href="{value}">{value}</a>'
            output[key] = value
        return output


def iter_jobs(where_group: str | None = None) -> Iterator[Job]:
    """Get jobs."""
    logger.debug("Get jobs from database")

    query = """
        SELECT
            key, name, schedule, timezone, description, labels, metadata, enabled
        FROM job
        """

    if where_group:
        query += ' WHERE "group" = :group'
        params = {"group": where_group}
    else:
        params = {}

    db = cron_times.db.get_db()
    with closing(db.cursor()) as cur:
        cur.execute(query, params)

        for (
            key,
            name,
            schedule,
            timezone,
            description,
            labels,
            metadata,
            enabled,
        ) in cur:
            yield Job(
                key=key,
                name=name,
                schedule=schedule,
                timezone=timezone,
                description=description,
                labels=labels,
                metadata=metadata,
                enabled=enabled,
            )


@click.command("init-db")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING"], False),
    default="INFO",
    help="Set log level.",
)
def command_init_db(log_level: int) -> None:
    """Initialize the database."""
    cron_times.logging.setup_logging(log_level)
    init_db()


def init_db():
    logger.info("Initializing database at %s", flask.current_app.config["DATABASE"])

    db = get_db()
    db.executescript(
        """
        DROP TABLE IF EXISTS job;

        CREATE TABLE job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            "group" TEXT NOT NULL,
            key TEXT NOT NULL,

            name TEXT NOT NULL,
            schedule TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            description TEXT,
            labels TEXT,
            metadata TEXT,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            UNIQUE ("group", key)
        );
        """
    )

    logger.info("Database initialized")

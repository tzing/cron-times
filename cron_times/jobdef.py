from __future__ import annotations

import json
import logging
import sys
import textwrap
import typing
import zoneinfo
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

import click
import croniter
import pydantic
import tomlkit

import cron_times.db
import cron_times.logging

if typing.TYPE_CHECKING:
    from typing import Iterator

    from tomlkit.items import AoT

FieldName = Literal[
    "name", "schedule", "timezone", "description", "labels", "metadata", "enabled"
]

ALL_FIELDS = {
    "name",
    "schedule",
    "timezone",
    "description",
    "labels",
    "metadata",
    "enabled",
}


logger = logging.getLogger(__name__)


def _validate_cron_expr(v: str) -> str:
    try:
        croniter.croniter(v)
    except ValueError:
        raise ValueError(f"Invalid cron expression {v}") from None
    return v


def _validate_timezone(v: str) -> str:
    try:
        zoneinfo.ZoneInfo(v)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError(f"Invalid timezone '{v}'") from None
    return v


class JobSpec(pydantic.BaseModel):
    """Job definition specification that is validated and can be used to create a job."""

    raw_key: str | None = pydantic.Field(default=None, alias="key")
    """User input key."""

    name: str
    """Name of the job."""

    schedule: Annotated[str, pydantic.AfterValidator(_validate_cron_expr)]
    """Schedule in cron expression."""

    timezone: Annotated[str, pydantic.AfterValidator(_validate_timezone)] = "UTC"
    """Timezone for the schedule."""

    raw_description: str | None = pydantic.Field(default=None, alias="description")
    """Description of the job."""

    labels: list[str] = pydantic.Field(default_factory=list)
    """Labels for the job."""

    metadata: dict[str, pydantic.JsonValue] = pydantic.Field(default_factory=dict)
    """Metadata for the job."""

    enabled: bool = True
    """Whether the job is enabled."""

    @pydantic.computed_field
    @property
    def key(self) -> str:
        """Key for job. It uses inputted "key" if specified, otherwise "name"."""
        return self.raw_key or self.name

    @pydantic.computed_field
    @property
    def description(self) -> str | None:
        raw = self.raw_description or ""
        raw = raw.strip("\r\n")
        raw = textwrap.dedent(raw)
        return raw or None


class JobDefFileSpec(pydantic.BaseModel):
    job: list[JobSpec]


@click.command("read-file")
@click.argument("path", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="Recursively search for job definition files.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING"]),
    default="INFO",
    help="Set log level.",
)
def command_read_file(path: list[Path], recursive: bool, log_level: int):
    """Load job definitions into database."""
    cron_times.logging.setup_logging(log_level)
    read_file_to_db(path, recursive)


def read_file_to_db(path_list: list[Path], recursive: bool):
    # collect file paths
    config_files: set[Path] = set()
    for filepath in iter_files(path_list, recursive):
        if not filepath.is_file():
            logger.error(f"'{filepath}' is not a file.")
            sys.exit(2)
        config_files.add(filepath)

    logger.debug("%d config files found.", len(config_files))

    # parse config files
    for filepath in config_files:
        logger.debug(f"Start reading {filepath}")

        # read & parse
        with filepath.open("rb") as fd:
            raw_config = tomlkit.load(fd)

        try:
            config = JobDefFileSpec.model_validate(raw_config)
        except pydantic.ValidationError as e:
            logger.error(f"Failed to parse {filepath}: {e}")
            sys.exit(1)

        logger.info("Found %d jobs in %s", len(config.job), filepath)

        # save
        sync_jobs_to_db(
            group=filepath.stem,
            input_jobs=config.job,
            fields_to_merge=ALL_FIELDS,
        )


def iter_files(path_list: list[Path], recursive: bool) -> Iterator[Path]:
    if recursive:
        yield from path_list

    else:
        for path in path_list:
            if path.is_dir():
                yield from path.glob("**/*.toml")
            else:
                yield path


@click.command()
@click.argument("path", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="Recursively search for job definition files.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING"]),
    default="INFO",
    help="Set log level.",
)
def init_db_from(path: list[Path], recursive: bool, log_level: int):
    """Initialize the database and load job definitions from file(s)."""
    cron_times.logging.setup_logging(log_level)
    cron_times.db.init_db()
    read_file_to_db(path, recursive)


def sync_jobs_to_db(
    *,
    group: str,
    input_jobs: list[JobSpec],
    fields_to_merge: list[FieldName],
) -> None:
    """Sync jobs in database with inputted jobs."""
    # read jobs from db and covert to JobSpec to align the types
    existing_jobs = []
    for job in cron_times.db.iter_jobs(group):
        existing_jobs.append(
            JobSpec(
                key=job.key,
                name=job.name,
                schedule=job.schedule,
                timezone=job.timezone.key,
                description=job.raw_description,
                labels=job.labels,
                metadata=job.metadata,
                enabled=job.enabled,
            )
        )

    # merge jobs
    merged_jobs, keys_to_drop = merge_job_lists(
        existing_job_list=existing_jobs,
        new_job_list=input_jobs,
        fields_to_merge=fields_to_merge,
    )

    # delete jobs that are not in input
    db = cron_times.db.get_db()
    with closing(db.cursor()) as cur:
        cur.execute(
            """
            DELETE FROM job
            WHERE
                1 = 1
                AND "group" = '{group}'
                AND key IN ({keys})
            """.format(
                group=group,
                keys=", ".join(f"'{key}'" for key in keys_to_drop),
            )
        )
        db.commit()

    if cur.rowcount:
        logger.info("Deleted %d '%s' jobs", cur.rowcount, group)

    # upsert jobs
    with closing(db.cursor()) as cur:
        cur.executemany(
            """
            INSERT INTO job ("group", key, name, schedule, timezone, description, labels, metadata, enabled)
            VALUES (:group, :key, :name, :schedule, :timezone, :description, :labels, :metadata, :enabled)
            ON CONFLICT ("group", key) DO UPDATE SET
                name = excluded.name,
                schedule = excluded.schedule,
                timezone = excluded.timezone,
                description = excluded.description,
                labels = excluded.labels,
                metadata = excluded.metadata,
                enabled = excluded.enabled
            """,
            [
                {
                    "group": group,
                    "key": job.key,
                    "name": job.name,
                    "schedule": job.schedule,
                    "timezone": job.timezone,
                    "description": job.description,
                    "labels": json.dumps(job.labels),
                    "metadata": json.dumps(job.metadata),
                    "enabled": job.enabled,
                }
                for job in merged_jobs.values()
            ],
        )
        db.commit()

    logger.info("Upserted %d '%s' jobs", len(merged_jobs), group)


def sync_jobs_to_file(
    *,
    path: Path | str,
    input_jobs: list[JobSpec],
    fields_to_merge: list[FieldName],
):
    """Sync jobs in file with inputted jobs."""
    # read existing jobs
    path = Path(path)
    if path.is_file():
        logger.debug(f"Try parsing {path}")

        # read & parse
        with path.open("rb") as fd:
            raw_config: tomlkit.TOMLDocument = tomlkit.load(fd)

        try:
            config = JobDefFileSpec.model_validate(raw_config)
        except pydantic.ValidationError as e:
            logger.error(f"Failed to parse {path}: {e}")
            sys.exit(1)

        logger.debug("Parsed %d jobs from %s", len(config.job), path)

    else:
        config = JobDefFileSpec(job=[])

    # merge jobs
    merged_jobs, _ = merge_job_lists(
        existing_job_list=config.job,
        new_job_list=input_jobs,
        fields_to_merge=fields_to_merge,
    )

    # output
    # TODO preserve the formats & comments
    output_fields = (
        "key",
        "name",
        "schedule",
        "timezone",
        "description",
        "labels",
        "metadata",
        "enabled",
    )

    document = tomlkit.document()
    job_list: AoT = document.setdefault("job", tomlkit.aot())

    for job in merged_jobs.values():
        data = job.model_dump(include=output_fields)
        null_value_keys = [k for k, v in data.items() if v is None]
        for k in null_value_keys:
            del data[k]
        job_list.append(data)

    with path.open("w") as fd:
        tomlkit.dump(document, fd)

    logger.info("Write %d jobs to %s", len(merged_jobs), path)


def merge_job_lists(
    *,
    existing_job_list: list[JobSpec],
    new_job_list: list[JobSpec],
    fields_to_merge: list[FieldName],
) -> tuple[dict[str, JobSpec], set[str]]:
    existing_jobs = {job.key: job for job in existing_job_list}
    new_jobs = {job.key: job for job in new_job_list}

    fields_to_merge = set(fields_to_merge)

    # find items to be updated
    upsert_jobs = {}
    keys_to_update = set(existing_jobs) & set(new_jobs)
    for key in keys_to_update:
        exist_job = existing_jobs[key]
        new_job = new_jobs[key]
        upsert_jobs[key] = exist_job.model_copy(
            update={field: getattr(new_job, field) for field in fields_to_merge}
        )

    # find items to be added
    keys_to_add = set(new_jobs) - set(existing_jobs)
    for key in keys_to_add:
        upsert_jobs[key] = new_jobs[key]

    # find items to be drop
    keys_to_drop = set(existing_jobs) - set(new_jobs)

    return upsert_jobs, keys_to_drop

from __future__ import annotations

import logging

import click
import httpx
from flask import render_template_string
from pydantic import BaseModel, computed_field

from cron_times.job import Job
from cron_times.logging import setup_logging

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--account-id",
    type=click.INT,
    required=True,
    help="dbt Account ID",
)
@click.option(
    "--token",
    required=True,
    envvar="DBT_TOKEN",
    help="dbt API Token",
)
@click.option(
    "--project-id",
    type=click.INT,
    multiple=True,
    help="db project ID to be included. "
    "When not specified, all projects are included. "
    "This option can be used multiple times.",
)
@click.option(
    "--environment-id",
    type=click.INT,
    multiple=True,
    help="dbt environment ID to be included. "
    "When not specified, all environments are included. "
    "This option can be used multiple times.",
)
@click.option(
    "-f",
    "--update-field",
    multiple=True,
    type=click.Choice(
        [
            "name",
            "schedule",
            "description",
            "metadata",
        ]
    ),
    default=("name", "schedule"),
    show_default=True,
    help="Field(s) to be updated when same job exists. "
    "This option can be used multiple times.",
)
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
def read_dbt_cloud(
    account_id: int,
    token: str,
    project_id: list[int],
    environment_id: list[int],
    missing: str,
    update_field: list[str],
    log_level: int,
):
    """Read jobs from dbt cloud."""
    setup_logging(log_level)

    logger.info("Read jobs from dbt cloud")
    logger.debug("account id: %s", account_id)
    logger.debug("project id(s): %s", project_id)
    logger.debug("environment id(s): %s", environment_id)

    # list jobs
    response = httpx.get(
        url=f"https://cloud.getdbt.com/api/v2/accounts/{account_id}/jobs/",
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        },
    )
    response.raise_for_status()

    # parse response
    jobs = []
    for data in response.json().get("data", []):
        dbt_job = DbtJob(**data)

        # filter: only return selected project id and environment ids
        if project_id and dbt_job.project_id not in project_id:
            logger.debug(
                "Skip #%d (%s): not selected project (%d)",
                dbt_job.id,
                dbt_job.name,
                dbt_job.project_id,
            )
            continue

        if environment_id and dbt_job.environment_id not in environment_id:
            logger.debug(
                "Skip #%d (%s): not selected environment (%d)",
                dbt_job.id,
                dbt_job.name,
                dbt_job.environment_id,
            )
            continue

        # skip if job is not scheduled
        if not dbt_job.triggers.schedule:
            logger.debug("Skip #%d (%s): not scheduled", dbt_job.id, dbt_job.name)
            continue

        ct_job = Job(
            name=dbt_job.name,
            schedule=dbt_job.schedule.cron,
            description=render_template_string(
                DESCRIPTION_TEMPLATE,
                job=dbt_job,
            ),
            labels=["dbt cloud"],
            metadata={
                "account id": dbt_job.account_id,
                "project id": dbt_job.project_id,
                "environment id": dbt_job.environment_id,
                "job id": dbt_job.id,
                "url": dbt_job.url,
            },
        )

        if dbt_job.dbt_version:
            ct_job.metadata["version"] = dbt_job.dbt_version

        jobs.append(ct_job)

    # save
    Job.objects_sync(
        group=f"dbt-cloud-{account_id}",
        jobs=jobs,
        update_fields=update_field,
        missing=missing,
    )


DESCRIPTION_TEMPLATE = """
{{ job.description }}

{% if job.execute_steps %}
```bash
{% for cmd in job.execute_steps %}
{{ cmd }}
{% endfor %}
```
{% endif %}
"""


class Triggers(BaseModel):
    schedule: bool


class Schedule(BaseModel):
    cron: str


class DbtJob(BaseModel):
    id: int
    account_id: int
    dbt_version: str | None
    description: str | None = None
    environment_id: int
    execute_steps: list[str]
    name: str
    project_id: int
    schedule: Schedule | None = None
    triggers: Triggers

    @computed_field
    @property
    def url(self) -> str:
        return f"https://cloud.getdbt.com/deploy/{self.account_id}/projects/{self.project_id}/jobs/{self.id}/"

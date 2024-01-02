from __future__ import annotations

import logging

import click
import httpx
from flask import render_template_string
from pydantic import BaseModel, computed_field

from cron_times.jobdef import JobSpec, sync_jobs_to_db, sync_jobs_to_file
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
    "-o",
    "--output",
    default=":db",
    show_default=True,
    help="Output destination. Use ':db' to save to database.",
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
    output: str,
    update_field: list[str],
    log_level: int,
):
    """Read jobs from dbt cloud."""
    setup_logging(log_level)

    logger.info("Read jobs from dbt cloud")
    logger.debug("account id: %s", account_id)
    logger.debug("project id(s): %s", project_id)
    logger.debug("environment id(s): %s", environment_id)

    # prepare http client
    http_client = httpx.Client(
        base_url="https://cloud.getdbt.com/",
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        },
    )

    # list accounts
    account_name = get_account_name(http_client, account_id)
    project_names = get_project_names(http_client, account_id, project_id)
    environment_names = get_environment_names(
        http_client, account_id, project_names, environment_id
    )

    def add_comment(key: str, context: dict[str, str]) -> str:
        if name := context.get(key):
            return f"{name} ({key})"
        return str(key)

    # list jobs
    response = http_client.get(url=f"api/v2/accounts/{account_id}/jobs/")
    response.raise_for_status()

    jobs = []
    for data in response.json().get("data", []):
        dbt_job = DbtJob.model_validate(data)

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

        ct_job = JobSpec(
            key=str(dbt_job.id),
            name=dbt_job.name,
            schedule=dbt_job.schedule.cron,
            description=render_template_string(
                DESCRIPTION_TEMPLATE,
                job=dbt_job,
            ),
            labels=["dbt cloud"],
            metadata={
                "account": f"{account_name} ({account_id})",
                "project": add_comment(dbt_job.project_id, project_names),
                "environment": add_comment(dbt_job.environment_id, environment_names),
                "job": f"{dbt_job.name} ({dbt_job.id})",
                "url": dbt_job.url,
            },
        )

        if dbt_job.dbt_version:
            ct_job.metadata["version"] = dbt_job.dbt_version

        jobs.append(ct_job)

    # save
    if output == ":db":
        sync_jobs_to_db(
            group=f"dbt-cloud:{account_id}",
            input_jobs=jobs,
            fields_to_merge=update_field,
        )
    else:
        sync_jobs_to_file(
            path=output,
            input_jobs=jobs,
            fields_to_merge=update_field,
        )


def get_account_name(http_client: httpx.Client, account_id: int) -> str:
    response = http_client.get("/api/v3/accounts/")
    response.raise_for_status()

    for data in response.json().get("data", []):
        if account_id == data["id"]:
            return data["name"]


def get_project_names(
    http_client: httpx.Client, account_id: int, project_ids: list[int]
) -> dict[int, str]:
    response = http_client.get(f"/api/v3/accounts/{account_id}/projects/")
    response.raise_for_status()

    project_names = {}
    for data in response.json().get("data", []):
        if project_ids and data["id"] not in project_ids:
            continue
        project_names[data["id"]] = data["name"]

    return project_names


def get_environment_names(
    http_client: httpx.Client,
    account_id: int,
    project_ids: list[int],
    environment_ids: list[int],
):
    environment_names = {}
    for project_id in project_ids:
        response = http_client.get(
            f"/api/v3/accounts/{account_id}/projects/{project_id}/environments/"
        )
        response.raise_for_status()

        for data in response.json().get("data", []):
            if environment_ids and data["id"] not in environment_ids:
                continue
            environment_names[data["id"]] = data["name"]

    return environment_names


DESCRIPTION_TEMPLATE = """
{{ job.description }}

{% if job.execute_steps -%}
```bash
{% for cmd in job.execute_steps -%}
{{ cmd }}
{% endfor -%}
```
{% endif -%}
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

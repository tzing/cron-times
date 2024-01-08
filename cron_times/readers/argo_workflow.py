from __future__ import annotations

import datetime
import logging

import click
import httpx
from pydantic import BaseModel, Field

from cron_times.jobdef import JobSpec, sync_jobs_to_db, sync_jobs_to_file
from cron_times.logging import setup_logging

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--base-url",
    required=True,
    envvar="ARGO_BASE_URL",
    help="Base URL to Argo Workflow server.",
)
@click.option(
    "--namespace",
    default="default",
    show_default=True,
    help="Namespace to read jobs from.",
)
@click.option(
    "--token",
    envvar="ARGO_TOKEN",
    help="Bearer token for authentication to Argo Workflow server. Optional.",
)
@click.option(
    "-o",
    "--output",
    default=":db",
    show_default=True,
    help="Output destination. Use ':db' to save to database.",
)
@click.option(
    "--exclude-suspended",
    is_flag=True,
    help="Include suspended jobs. Default is to include suspended jobs.",
)
@click.option(
    "--label-selector",
    multiple=True,
    help="Label selector to filter jobs. This option can be used multiple times.",
)
@click.option(
    "--field-selector",
    multiple=True,
    help="Field selector to filter jobs. This option can be used multiple times.",
)
@click.option(
    "-f",
    "--update-field",
    multiple=True,
    type=click.Choice(
        ["name", "schedule", "timezone", "description", "metadata", "enabled"]
    ),
    default=("schedule", "timezone", "enabled"),
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
def read_argo_workflow(
    base_url: str,
    namespace: str,
    token: str | None,
    exclude_suspended: bool,
    label_selector: list[str],
    field_selector: list[str],
    output: str,
    update_field: list[str],
    log_level: int,
):
    """Read Cron Workflow from Argo Workflow service."""
    setup_logging(log_level)

    logger.info("Read Cron Workflow from Argo")
    logger.debug("base url: %s", base_url)
    logger.debug("namespace: %s", namespace)
    logger.debug("label selector(s): %s", label_selector)
    logger.debug("field selector(s): %s", field_selector)

    # query
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    httpx_client = httpx.Client(base_url=base_url, headers=headers)

    response = httpx_client.get(
        f"/api/v1/cron-workflows/{namespace}",
        params={
            "listOptions.labelSelector": ",".join(label_selector),
            "listOptions.fieldSelector": ",".join(field_selector),
        },
    )
    response.raise_for_status()

    normalized_base_url = response.url.copy_with(path=None, query=None, fragment=None)

    # parse
    jobs = []
    for item in response.json().get("items", []):
        cw = CronWorkflow.model_validate(item)

        if exclude_suspended and cw.spec.suspend:
            continue

        metadata = {
            "uid": cw.metadata.uid,
            "name": cw.metadata.name,
            "created at": None,
            "generation": cw.metadata.generation,
            "namespace": cw.metadata.namespace,
            "url": f"{normalized_base_url}/cron-workflows/{cw.metadata.namespace}/{cw.metadata.name}",
        }

        if cw.metadata.creationTimestamp:
            metadata["created at"] = cw.metadata.creationTimestamp.isoformat()
        else:
            metadata.pop("created at")

        ct_job = JobSpec(
            key=cw.metadata.uid,
            name=cw.metadata.name,
            schedule=cw.spec.schedule,
            timezone=cw.spec.timezone,
            labels=["argo workflow"],
            metadata=metadata,
            enabled=not cw.spec.suspend,
        )
        jobs.append(ct_job)

    # save
    if output == ":db":
        sync_jobs_to_db(
            group=f"argo-workflow:{namespace}",
            input_jobs=jobs,
            fields_to_merge=update_field,
        )
    else:
        sync_jobs_to_file(
            path=output,
            input_jobs=jobs,
            fields_to_merge=update_field,
        )


class ObjectMeta(BaseModel):
    """
    https://argo-workflows.readthedocs.io/en/latest/fields/#objectmeta
    """

    name: str
    uid: str
    creationTimestamp: datetime.datetime | None = None
    generation: int
    namespace: str


class Parameter(BaseModel):
    """
    https://argo-workflows.readthedocs.io/en/latest/fields/#parameter
    """

    name: str
    description: str | None = None
    value: str


class Arguments(BaseModel):
    """
    https://argo-workflows.readthedocs.io/en/latest/fields/#arguments
    """

    parameters: list[Parameter] = Field(default_factory=list)


class WorkflowSpec(BaseModel):
    """
    WorkflowSpec

    https://argo-workflows.readthedocs.io/en/latest/fields/#workflowspec
    """

    entrypoint: str | None = None
    arguments: Arguments


class CronWorkflowSpec(BaseModel):
    """
    CronWorkflowSpec

    https://argo-workflows.readthedocs.io/en/latest/fields/#cronworkflowspec
    """

    schedule: str
    suspend: bool = False
    timezone: str
    workflowSpec: WorkflowSpec


class CronWorkflow(BaseModel):
    """
    CronWorkflow

    https://argo-workflows.readthedocs.io/en/latest/fields/#cronworkflow
    """

    metadata: ObjectMeta
    spec: CronWorkflowSpec

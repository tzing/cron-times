import logging

import httpx
import jinja2

logger = logging.getLogger(__name__)


def get_tasks(
    account_id: int,
    token: str,
    wanted_project_ids: list[int] = None,
    wanted_environment_ids: list[int] = None,
    labels: list[str] = None,
):
    wanted_project_ids = set(wanted_project_ids or [])
    wanted_environment_ids = set(wanted_environment_ids or [])
    labels = tuple(labels or [])

    logger.info(
        "Read dbt cloud tasks from account %d; filtering- project %s, environment %s",
        account_id,
        sorted(wanted_project_ids),
        sorted(wanted_environment_ids),
    )

    # list jobs
    resp = httpx.get(
        url=f"https://cloud.getdbt.com/api/v2/accounts/{account_id}/jobs/",
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        },
    )

    data = resp.json().get("data", [])
    logger.info("Read %d raw tasks", len(data))

    # prepare jinja
    env = jinja2.Environment()
    tmpl = env.from_string(DESC_TEMPLATE)

    # build task
    for task in data:
        task_id = task["id"]

        # filter: only return selected project id and environment ids
        project_id = task["project_id"]
        if wanted_project_ids and project_id not in wanted_project_ids:
            logger.info(
                "Skip dbt#%d (%s): not selected project (%d)",
                task_id,
                task["name"],
                project_id,
            )
            continue

        environment_id = task["environment_id"]
        if wanted_environment_ids and environment_id not in wanted_environment_ids:
            logger.info(
                "Skip dbt#%d (%s): not selected environment (%d)",
                task_id,
                task["name"],
                environment_id,
            )
            continue

        # filter: exclude jobs without schedule trigger
        if not task["triggers"]["schedule"]:
            logger.info("Skip dbt#%d (%s): no schedule trigger", task_id, task["name"])
            continue

        yield {
            "name": task["name"],
            "_id": task_id,
            "schedule": task["schedule"]["cron"],
            "labels": labels,
            "description": tmpl.render(task).strip(),
            "metadata": {
                "project": project_id,
                "environment": environment_id,
                "url": f"https://cloud.getdbt.com/deploy/{account_id}/projects/{project_id}/jobs/{task_id}",
            },
        }


DESC_TEMPLATE = """
dbt job that runs following command:

```bash
{%- if execute_steps %}
{{ execute_steps | join('\n') }}
{%- else %}
(no command set)
{%- endif %}
```

{% if generate_docs -%}
And it generate docs on run.
{% endif %}
"""

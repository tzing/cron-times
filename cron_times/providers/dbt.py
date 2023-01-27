import logging

import httpx
import jinja2

logger = logging.getLogger(__name__)


def get_tasks(
    account_id: int,
    token: str,
    project_ids: list[int] = None,
    environment_ids: list[int] = None,
    default_labels: list[str] = None,
):
    project_ids = set(project_ids or [])
    environment_ids = set(environment_ids or [])
    default_labels = tuple(default_labels or [])

    logger.info(
        "Read dbt cloud tasks from account %d; filtering- project %s, environment %s",
        account_id,
        sorted(project_ids),
        sorted(environment_ids),
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
        # filter: only return selected project id and environment ids
        if project_ids and task["project_id"] not in project_ids:
            logger.info(
                "Skip dbt#%d (%s): not selected project (%d)",
                task["id"],
                task["name"],
                task["project_id"],
            )
            continue
        if environment_ids and task["environment_id"] not in environment_ids:
            logger.info(
                "Skip dbt#%d (%s): not selected environment (%d)",
                task["id"],
                task["name"],
                task["environment_id"],
            )
            continue

        # filter: exclude jobs without schedule trigger
        if not task["triggers"]["schedule"]:
            logger.info(
                "Skip dbt#%d (%s): no schedule trigger", task["id"], task["name"]
            )
            continue

        yield {
            "name": task["name"],
            "_id": task["id"],
            "schedule": task["schedule"]["cron"],
            "labels": default_labels,
            "description": tmpl.render(task).strip(),
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

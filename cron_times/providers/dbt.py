import httpx
import jinja2


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

    # list jobs
    resp = httpx.get(
        url=f"https://cloud.getdbt.com/api/v2/accounts/{account_id}/jobs/",
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        },
    )

    # prepare jinja
    env = jinja2.Environment()
    tmpl = env.from_string(DESC_TEMPLATE)

    # build task
    output = []
    for task in resp.json().get("data", []):
        # don't include manual job(s)
        if not task["triggers"]["schedule"]:
            continue

        # filter: only return selected project id and environment ids
        if project_ids and task["project_id"] not in project_ids:
            continue
        if environment_ids and task["environment_id"] not in environment_ids:
            continue

        output.append(
            {
                "name": task["name"],
                "_id": task["id"],
                "schedule": task["schedule"]["cron"],
                "labels": default_labels,
                "description": tmpl.render(task).strip(),
            }
        )

    return output


DESC_TEMPLATE = """
dbt job that runs following command:

```bash
{% if execute_steps %}
{% for step in execute_steps %}
{{ step }}
{%- endfor %}
{% else %}
(no command set)
{%- endif %}
```

{% if generate_docs -%}
And it generate docs on run.
{% endif %}
"""

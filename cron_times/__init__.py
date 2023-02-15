import datetime
import functools
import logging
import os
import uuid
import zoneinfo
from http import HTTPStatus

import croniter
import flask
import mistune

import cron_times.base
import cron_times.tasks
import cron_times.timezone

TASK_DIR = os.getenv("CRONTIMES_TASK_DIR", "tasks")

app = flask.Flask(__name__)
app.jinja_env.add_extension("pypugjs.ext.jinja.PyPugJSExtension")

app.register_blueprint(cron_times.base.api, url_prefix="/api")

__tasks = None
__indexes = None

logger = logging.getLogger(__name__)


@app.route("/")
def timetable():
    # decide time range
    now = datetime.datetime.now()
    query_time_start = now - datetime.timedelta(days=1)
    query_time_end = now + datetime.timedelta(days=2)

    # get tasks
    tasks, indexes = get_tasks()

    # get jobs in the selected time range
    unsorted_jobs = []
    for task in tasks:
        timezone = zoneinfo.ZoneInfo(task["timezone"])
        for dt in croniter.croniter_range(
            query_time_start, query_time_end, task["schedule"]
        ):
            job = task.copy()
            job["datetime"] = dt.replace(tzinfo=timezone)
            unsorted_jobs.append(job)

    # sort
    jobs = sorted(unsorted_jobs, key=lambda d: d["datetime"])

    return flask.render_template(
        "timetable.pug",
        title=os.getenv("CRONTIMES_PAGE_TITLE", "Cronjobs"),
        timezones=cron_times.timezone.list_timezones(),
        indexes=indexes,
        jobs=jobs,
    )


@app.route("/healthz")
def health_check():
    tasks = cron_times.tasks.load_tasks(TASK_DIR)
    data = flask.render_template("clock.txt", n_task=len(tasks))
    return flask.Response(
        status=HTTPStatus.OK,
        response=data,
        content_type="text/plain; charset=utf-8",
    )


@app.template_filter("markdown")
def render_markdown(s: str) -> str | None:
    if not s:
        return None
    md = mistune.create_markdown(
        plugins=["strikethrough", "footnotes", "table", "url", "task_lists"]
    )
    return md(s)


def get_tasks():
    global __tasks, __indexes
    if __tasks:
        return __tasks, __indexes

    # get tasks
    tasks = cron_times.tasks.load_tasks(TASK_DIR)

    # indexing
    def gen_index():
        return f"index-{uuid.uuid4()}"

    indexes: dict[tuple[int, str], str] = {
        # key fmt in (int, str)
        #               \    \-- name
        #                \------ sort key
    }
    for task in tasks:
        # per task index
        task_name: str = task["name"]
        task_index = gen_index()
        indexes[0, task_name.casefold()] = "Task", task_name, task_index

        # storage
        task["indexes"] = {task_index}

        # per label index
        for label in task["labels"]:
            label_key = 1, label.casefold()
            if label_key in indexes:
                _, _, label_index = indexes[label_key]
            else:
                label_index = gen_index()
                indexes[label_key] = "Label", label, label_index
            task["indexes"].add(label_index)

    sorted_indexes = {}
    for key in sorted(indexes.keys()):
        category, name, index = indexes[key]
        sorted_indexes[f"{category}: {name}"] = index

    if not app.debug:  # always reload in debug
        __tasks = tasks
        __indexes = sorted_indexes

    return tasks, sorted_indexes

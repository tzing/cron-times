import datetime
import enum
import logging
import os
import uuid
import zoneinfo
from http import HTTPStatus

import croniter
import flask

import cron_times.base
import cron_times.file
import cron_times.timezone

app = flask.Flask(__name__)
app.jinja_env.add_extension("pypugjs.ext.jinja.PyPugJSExtension")

app.register_blueprint(cron_times.base.api, url_prefix="/api")

logger = logging.getLogger(__name__)
__tasks = None


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
    data = flask.render_template("clock.txt")
    return flask.Response(
        status=HTTPStatus.OK,
        response=data,
        content_type="text/plain; charset=utf-8",
    )


def get_tasks():
    """Cache `get_tasks` for production."""
    global __tasks
    if not app.debug and __tasks:
        return __tasks
    __tasks = _get_tasks()
    return __tasks


def _get_tasks():
    """Load tasks and generate indexes for filter."""
    # load
    TASK_DIR = os.getenv("CRONTIMES_TASK_DIR", "tasks")
    tasks = cron_times.file.load_all_tasks_from_file(TASK_DIR)

    # generate index for filter
    # dict[type, key] = (internal id, name)
    global_indexes: dict[tuple[IndexType, str], tuple[str, str]] = {}

    def set_index(type_: IndexType, key: str, name: str) -> str:
        index, _ = global_indexes.setdefault(
            (type_, key), (f"index-{uuid.uuid4()}", name)
        )
        return index

    for task in tasks:
        # stores all index id that is related to this task
        task["indexes"] = task_indexes = set()

        # set per task index
        index = set_index(IndexType.Task, task["key"], task["name"])
        task_indexes.add(index)

        # per label index
        for label in task["labels"]:
            index = set_index(IndexType.Label, label["key"], label["text"])
            task_indexes.add(index)

    # sort indexes for prettier display
    output_filters = []
    for type_, key in sorted(global_indexes.keys()):
        index, name = global_indexes[type_, key]
        output_filters.append((f"{type_.name}: {name}", index))

    return tasks, output_filters


class IndexType(enum.IntEnum):
    Task = enum.auto()
    Label = enum.auto()

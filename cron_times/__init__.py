import datetime
import functools
import logging
import os
import uuid
import zoneinfo

import croniter
import flask
import markdown2

import cron_times.tasks

TASK_DIR = os.getenv("CRONTIMES_TASK_DIR", "tasks")

app = flask.Flask(__name__)
app.jinja_env.add_extension("pypugjs.ext.jinja.PyPugJSExtension")

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
        title=os.getenv("TIMETABLE_TITLE", "Cronjobs"),
        timezones=get_timezones(),
        indexes=indexes,
        jobs=jobs,
    )


@functools.cache
def get_timezones() -> list[dict]:
    now = datetime.datetime.utcnow()

    parsed_timezones = {}
    for name in zoneinfo.available_timezones():
        # short name
        *_, short_name = name.split("/")
        short_name = short_name.replace("_", " ")

        if short_name in parsed_timezones:
            continue

        # offset
        zone = zoneinfo.ZoneInfo(name)
        delta = zone.utcoffset(now)  # this api take care of daylight saving
        offset = delta.days * 86400 + delta.seconds
        hh = offset // 3600
        mm = (offset - hh * 3600) // 60

        if name.startswith("Etc/GMT"):
            continue  # workaround: don't know why GMT offsets are negative

        parsed_timezones[short_name] = {
            "name": name,
            "short_name": short_name,
            "offset": offset,
            "offset_display": f"{hh:+03d}:{mm:02d}",
        }

    output = sorted(
        parsed_timezones.values(),
        key=lambda tz: (tz["offset"], tz["short_name"]),
    )

    return output


@app.template_filter("markdown")
def render_markdown(s: str) -> str | None:
    if not s:
        return None
    return markdown2.markdown(
        s,
        safe_mode=True,
        extras=[
            "code-friendly",
            "fenced-code-blocks",
            "strike",
            "tables",
        ],
    )


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

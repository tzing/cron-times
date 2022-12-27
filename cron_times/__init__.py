import datetime
import functools
import glob
import logging
import os
import zoneinfo
from pathlib import Path

import croniter
import flask
import markdown2
import markupsafe
import yaml

YAML_EXTENSIONS = (".yaml", ".yml")


app = flask.Flask(__name__)
app.jinja_env.add_extension("pypugjs.ext.jinja.PyPugJSExtension")

logger = logging.getLogger(__name__)


@functools.cache
def get_schedule():
    # find files
    base_dir = Path(os.getenv("TIMETABLE_SCHEDULE_DIR", "jobs/"))
    base_dir = base_dir.resolve().absolute()
    logger.info("Search for schedules in %s", base_dir)

    files: list[Path] = []
    for ext in YAML_EXTENSIONS:
        for filename in glob.glob(root_dir=base_dir, pathname="**" + ext):
            files.append(base_dir / filename)

    logger.info("Found %d files: %s", len(files), ", ".join(str(p) for p in files))

    # load
    schedules = []
    for filepath in files:
        with filepath.open("rb") as fd:
            data = yaml.safe_load(fd)

        if not isinstance(data, list):
            logger.warning("Schedule file %s is not a list", filepath)
            continue

        for item in data:
            if isinstance(item, dict):
                name = item.get("name")
                schedule = item.get("schedule")

                desc = item.get("description") or None
                labels = item.get("labels") or []

                if name and schedule:
                    schedules.append(
                        {
                            "name": name,
                            "schedule": schedule,
                            "description": desc,
                            "labels": labels,
                        }
                    )
                    continue

            logger.warning("Item %s in file %s is not a valid object", item, filepath)

    logger.info("Load %s schedules", len(schedules))
    return schedules


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


@functools.cache
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


@app.route("/")
def timetable():
    now = datetime.datetime.now()
    query_time_start = now - datetime.timedelta(days=1)
    query_time_end = now + datetime.timedelta(days=2)

    unsorted_jobs = []
    for item in get_schedule():
        for dt in croniter.croniter_range(
            query_time_start, query_time_end, item["schedule"]
        ):
            unsorted_jobs.append(
                {
                    "name": markupsafe.Markup(item["name"]),
                    "datetime": dt,
                    "description": render_markdown(item["description"]),
                    "labels": item["labels"],
                    "schedule": item["schedule"],
                }
            )

    jobs = sorted(unsorted_jobs, key=lambda d: d["datetime"])

    return flask.render_template(
        "timetable.pug",
        title=os.getenv("TIMETABLE_TITLE", "Cronjobs"),
        timezones=get_timezones(),
        jobs=jobs,
    )

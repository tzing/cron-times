from __future__ import annotations

import datetime
import functools
import html
import re
import typing
import uuid
import zoneinfo

import croniter
import flask
import rapidfuzz.process

import cron_times.db

if typing.TYPE_CHECKING:
    from typing import Literal

    from cron_times.db import Job


bp = flask.Blueprint("cron_times", __name__)


@bp.route("/")
def home():
    return flask.render_template("home.html")


@bp.route("/timezones")
def get_timezones():
    time_zones = list_timezones()

    # filter when requested
    if query := flask.request.args.get("query"):
        selected = {}

        query_text = query.strip().lower()
        query_dict = {name: name.lower() for name in time_zones}

        for _, _, index in rapidfuzz.process.extract(query_text, query_dict, limit=10):
            selected[index] = time_zones[index]

        time_zones = selected

    # format the offsets
    def fmt_offset(d: datetime.timedelta) -> str:
        seconds = d.total_seconds()
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours:+03d}:{minutes:02d}"

    return "".join(
        flask.render_template(
            "timezone-item.html",
            name=name,
            offset=fmt_offset(delta),
            is_current=name == flask.request.args.get("currentTimeZone"),
        )
        for name, delta in time_zones.items()
    )


@functools.cache
def list_timezones() -> dict[str, datetime.timedelta]:
    now = datetime.datetime.utcnow()

    # list all timezones & their offsets
    time_zones = []
    for zone_name in zoneinfo.available_timezones():
        timezone = zoneinfo.ZoneInfo(zone_name)
        delta = timezone.utcoffset(now)

        if zone_name.startswith("Etc/GMT"):
            # Etc/GMT signs are intentionally inverted
            # https://en.wikipedia.org/wiki/Tz_database#Area
            delta = datetime.timedelta(seconds=-delta.total_seconds())

        time_zones.append((delta, zone_name))

    return {name: delta for delta, name in sorted(time_zones)}


@bp.route("/plans")
def get_plans():
    # setup variables
    display_timezone = flask.request.args.get("currentTimeZone")
    if display_timezone:
        display_timezone = zoneinfo.ZoneInfo(display_timezone)
    else:
        display_timezone = datetime.UTC

    job_filter = clean_query_text(flask.request.args.get("query"))

    lookbehind_seconds, lookahead_seconds = get_timerange_seconds()
    now = datetime.datetime.now().astimezone()
    query_time_start = now - datetime.timedelta(seconds=lookbehind_seconds)
    query_time_end = now + datetime.timedelta(seconds=lookahead_seconds)

    # get plans
    jobs = cron_times.db.iter_jobs()
    plans: list[tuple[datetime.datetime, Job | Literal[":now"]]] = []
    for job in jobs:
        if not match_job(job_filter, job):
            continue
        start = query_time_start.astimezone(job.timezone)
        end = query_time_end.astimezone(job.timezone)
        for time in croniter.croniter_range(start, end, job.schedule):
            plans.append((time, job))

    # limit the number of plans returned
    plans = trim_returned_plans(plans)
    plans.append((now, ":now"))
    plans = sorted(plans, key=lambda x: x[0])

    # render
    cards = []
    for time, job in plans:
        time = time.astimezone(display_timezone)

        if job == ":now":
            card = flask.render_template(
                "plan-item-now.html",
                time=time,
            )
        else:
            card = flask.render_template(
                "plan-item.html",
                uuid=uuid.uuid1(),
                time=time,
                job=job,
            )

        cards.append(card)

    return "".join(cards)


def match_job(query: str, job: Job) -> bool:
    if not query:
        return True

    if query in clean_query_text(job.name):
        return True
    if query in clean_query_text(job.raw_description):
        return True
    for label in job.labels:
        if query in clean_query_text(label):
            return True
    for value in job.metadata.values():
        if query in clean_query_text(str(value)):
            return True

    return False


@bp.route("/query-options")
def get_query_options():
    options = set()

    for job in cron_times.db.iter_jobs():
        options.add(clean_query_text(job.name))
        for label in job.labels:
            options.add(clean_query_text(label))

    return "\n".join(f'<option value="{html.escape(o)}">' for o in sorted(options))


@functools.lru_cache(4096)
def clean_query_text(s: str) -> str:
    if not s:
        return ""

    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    s = s.casefold()
    return s


@functools.cache
def get_timerange_seconds():
    lookbehind_seconds = int(flask.current_app.config["TIMETABLE_LOOKBEHIND_SECONDS"])
    lookahead_seconds = int(flask.current_app.config["TIMETABLE_LOOKAHEAD_SECONDS"])
    return lookbehind_seconds, lookahead_seconds


def trim_returned_plans(plans: list[tuple[datetime.datetime, Job]]):
    max_item_count = int(flask.current_app.config["TIMETABLE_MAX_ITEMS"])
    if len(plans) <= max_item_count:
        return plans

    # get the number of plans to be returned in each time range
    lookbehind_seconds, lookahead_seconds = get_timerange_seconds()
    ratio_behind = lookbehind_seconds / (lookahead_seconds + lookbehind_seconds)

    count_behind = round(max_item_count * ratio_behind)
    count_ahead = max_item_count - count_behind

    # split the plans into two groups
    now = datetime.datetime.now().astimezone()
    plans_behind = []
    plans_ahead = []
    for time, job in plans:
        if time < now:
            plans_behind.append((time, job))
        else:
            plans_ahead.append((time, job))

    # trim each group
    plans_behind = sorted(plans_behind, key=lambda x: x[0])
    plans_behind = plans_behind[-count_behind:]

    plans_ahead = sorted(plans_ahead, key=lambda x: x[0])
    plans_ahead = plans_ahead[:count_ahead]

    return plans_behind + plans_ahead

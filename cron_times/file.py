import glob
import logging
import typing
import zoneinfo
from pathlib import Path
from typing import Any

import croniter
import markupsafe
import mistune
import ruamel.yaml

if typing.TYPE_CHECKING:
    import os

DEFAULT_TIMEZONE = "UTC"
BADGE_COLORS = {
    "blue",
    "purple",
    "pink",
    "red",
    "orange",
    "yellow",
    "green",
    "teal",
    "cyan",
    "white",
    "black",
}

logger = logging.getLogger(__name__)
__md = None


def load_all_tasks_from_file(task_dir: "os.PathLike") -> list[dict[str, typing.Any]]:
    """Read all tasks in the directory."""
    # find files
    task_dir = Path(task_dir)
    files: list[Path] = []
    for name in glob.glob(root_dir=task_dir, pathname="**.yaml", recursive=True):
        files.append(task_dir / name)

    logger.info("Found %d files: %s", len(files), ", ".join(str(p) for p in files))

    # read files
    output = []
    for filepath in files:
        output.extend(load_task_definition_file(filepath))

    logger.info("Load %s schedules", len(output))
    return output


def load_task_definition_file(filepath: "os.PathLike") -> list[dict[str, typing.Any]]:
    """Read task file."""
    # load file
    with open(filepath, "rb") as fp:
        yaml = ruamel.yaml.YAML()
        tasks = yaml.load(fp)

    if not isinstance(tasks, list):
        logger.error("Task file %s is not a list.", filepath)
        return []

    # parse
    output = []
    for item in tasks:
        if parsed := parse_task(item):
            output.append(parsed)

    return output


def parse_task(data: dict) -> dict[str, Any] | None:
    # name
    if not (name := data.get("name")):
        logger.warning("Missing required field 'name'.")
        return

    name_display = markupsafe.escape(name)
    name_index_key = name.casefold()

    # schedule
    if not (schedule := data.get("schedule")):
        logger.warning("Missing required field 'schedule' in task %s", name)
        return

    if not is_valid_schedule(schedule):
        logger.warning("Bad schedule in task %s: %s", name, schedule)
        return

    # timezone
    if not (timezone := data.get("timezone")):
        logger.info("No timezone info in task %s. Use %s.", name, DEFAULT_TIMEZONE)
        timezone = DEFAULT_TIMEZONE

    if not is_valid_timezone(timezone):
        logger.warning(
            "Unknown timezone %s in task %s. Fallback to %s",
            timezone,
            name,
            DEFAULT_TIMEZONE,
        )
        timezone = DEFAULT_TIMEZONE

    # description
    description = render_markdown(data.get("description"))

    # labels
    labels = []
    for item in data.get("labels", []):
        if isinstance(item, str):
            text = item
            color = None
        elif isinstance(item, dict):
            text = item.get("text")
            color = item.get("color")
        else:
            logger.warning("Unrecognized label: %s", item)
            continue

        if color and color not in BADGE_COLORS:
            logger.warning("Unknown color: %s", color)
            color = None

        safe_text = markupsafe.escape(text)
        index_key = text.casefold()
        labels.append({"text": safe_text, "key": index_key, "color": color})

    return {
        "name": name_display,
        "key": name_index_key,
        "schedule": schedule,
        "timezone": timezone,
        "labels": labels,
        "description": description,
    }


def is_valid_schedule(s: str) -> bool:
    try:
        croniter.croniter(s)
    except croniter.CroniterBadCronError:
        return False
    return True


def is_valid_timezone(t: str) -> bool:
    try:
        zoneinfo.ZoneInfo(t)
    except zoneinfo.ZoneInfoNotFoundError:
        return False
    return True


def render_markdown(s: str) -> str | None:
    global __md
    if not s:
        return None
    if not __md:
        __md = mistune.create_markdown(
            plugins=["strikethrough", "footnotes", "table", "url", "task_lists"]
        )
    return __md(s)

import glob
import logging
import typing
import zoneinfo
from pathlib import Path

import croniter
import ruamel.yaml

if typing.TYPE_CHECKING:
    import os

DEFAULT_TIMEZONE = "UTC"

logger = logging.getLogger(__name__)


def load_tasks(task_dir: "os.PathLike") -> list[dict[str, typing.Any]]:
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
        output.extend(load_file(filepath))

    logger.info("Load %s schedules", len(output))
    return output


def load_file(filepath: "os.PathLike") -> list[dict[str, typing.Any]]:
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
    for task in tasks:
        if not isinstance(task, dict):
            logger.warning("Task must be a dict. Got %s.", type(task).__name__)
            continue

        # name
        if not (name := task.get("name")):
            logger.warning("Missing required field 'name'.")
            continue

        # schedule
        if not (schedule := task.get("schedule")):
            logger.warning("Missing required field 'schedule' in task %s", name)
            continue

        try:
            croniter.croniter(schedule)
        except croniter.CroniterBadCronError:
            logger.warning("Bad schedule in task %s: %s", name, schedule)
            continue

        # timezone
        if not (timezone := task.get("timezone")):
            logger.info("No timezone info in task %s. Use %s.", name, DEFAULT_TIMEZONE)
            timezone = DEFAULT_TIMEZONE

        try:
            zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError:
            logger.warning(
                "Unknown timezone %s in task %s. Fallback to %s",
                timezone,
                name,
                DEFAULT_TIMEZONE,
            )

        # output
        output.append(
            {
                "name": name,
                "schedule": schedule,
                "timezone": timezone,
                "labels": task.get("labels", []),
                "description": task.get("description"),
            }
        )

    return output

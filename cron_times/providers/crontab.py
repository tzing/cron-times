import logging
import os
import subprocess
from typing import Optional

import tzlocal


logger = logging.getLogger(__name__)


def get_tasks(user: Optional[str], labels: list[str]):
    logger.info("Read %s's crontab", user or "(current user)")

    # read
    crontab_cmd = ["crontab", "-l"]
    if user:
        crontab_cmd += ["-u", user]

    result = subprocess.run(crontab_cmd, stdout=subprocess.PIPE)

    logger.debug("Get output:\n%s", result.stdout.decode())

    # get tz
    timezone = tzlocal.get_localzone_name()
    logger.info("Get timezone: %s", timezone)

    # labels
    labels = list(labels)

    # parse
    for line in result.stdout.splitlines():
        sline = line.strip()
        if not sline or sline.startswith(b"#"):
            continue

        schedule, cmd = split_schedule(line.decode())
        yield {
            "name": get_name(cmd),
            "schedule": schedule,
            "timezone": timezone,
            "description": DESC_TEMPLATE.format(cmd=cmd),
            "labels": labels,
        }


def split_schedule(line: str) -> tuple[str, str]:
    minute, hour, day, month, weekday, cmd = line.split(maxsplit=5)
    return f"{minute} {hour} {day} {month} {weekday}", cmd


def get_name(cmd: str) -> str:
    prog, *_ = cmd.split(maxsplit=1)
    return os.path.basename(prog)


DESC_TEMPLATE = """\
Parsed from crontab:

```bash
{cmd}
```
"""

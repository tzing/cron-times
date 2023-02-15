import datetime
import zoneinfo

from .base import api


def list_timezones() -> list[dict]:
    """Listing IANA tz databases"""
    now = datetime.datetime.utcnow()

    # iter IANA tz databases
    timezones = {}
    for db in zoneinfo.available_timezones():
        # skip Etc series
        # Etc/GMT signs are intentionally inverted. For the rest (e.g. UTC) we
        # have an alternative db in non Etc region
        # ref: https://en.wikipedia.org/wiki/Tz_database#Area
        if db.startswith("Etc/"):
            continue

        # get region name
        # `America/New_York` -> `New York`
        *_, region = db.rsplit("/", maxsplit=1)
        region = region.replace("_", " ")

        # get offset
        tz = zoneinfo.ZoneInfo(db)
        delta = tz.utcoffset(now)
        offset = delta.days * 86400 + delta.seconds

        # some zone are duplicated. use (offset, region) pair to get unique list
        # e.g. `Asia/Singapore` and `Singapore`
        data = {"db": db, "region": region, "offset": offset}
        timezones[offset, region] = data

    # sort
    sorted_timezones = []
    for key in sorted(timezones):
        sorted_timezones.append(timezones[key])

    return sorted_timezones


@api.app_template_filter("to_readable_offset")
def format_offset(s: int) -> str:
    hh = s // 3600
    mm = (s - hh * 3600) // 60
    return f"{hh:+03d}:{mm:02d}"

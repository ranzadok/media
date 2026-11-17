"""Shabbat and holiday guard (Israel time).

No posting from Friday 12:00 until Saturday 23:00, none on a yom-tov day until 23:00,
and none on the eve of a yom-tov from 12:00.
"""
import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pyluach import dates  # required: without it holidays cannot be checked

IL = ZoneInfo("Asia/Jerusalem")
STEP = datetime.timedelta(minutes=15)


@lru_cache(maxsize=None)
def _yomtov(year: int) -> frozenset:
    out = set()
    d = datetime.date(year, 1, 1)
    while d.year == year:
        if dates.GregorianDate(d.year, d.month, d.day).festival(israel=True, include_working_days=False):
            out.add(d)
        d += datetime.timedelta(days=1)
    return frozenset(out)


def _is_yomtov(d: datetime.date) -> bool:
    return d in _yomtov(d.year)


def allowed(dt: datetime.datetime) -> tuple[bool, str]:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    local = dt.astimezone(IL)
    d, hm, wd = local.date(), local.hour + local.minute / 60, local.weekday()
    if wd == 4 and hm >= 12:
        return False, "שישי אחרי 12:00 (שבת)"
    if wd == 5 and hm < 23:
        return False, "שבת"
    if _is_yomtov(d) and hm < 23:
        return False, "חג"
    if _is_yomtov(d + datetime.timedelta(days=1)) and hm >= 12:
        return False, "ערב חג אחרי 12:00"
    return True, "ok"


def next_allowed(dt: datetime.datetime) -> datetime.datetime:
    cur = dt.astimezone(IL)
    for _ in range(4 * 24 * 10):  # at most 10 days ahead
        if allowed(cur)[0]:
            return cur
        cur = cur + STEP
        # snap to the quarter hour so results are stable
        cur = cur.replace(minute=(cur.minute // 15) * 15, second=0, microsecond=0)
    raise RuntimeError("no allowed time within 10 days")

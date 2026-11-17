from datetime import datetime
from zoneinfo import ZoneInfo
from publish.guard import allowed, next_allowed

IL = ZoneInfo("Asia/Jerusalem")
def t(*a): return datetime(*a, tzinfo=IL)

def test_friday_noon_boundary():
    assert allowed(t(2026, 11, 20, 11, 59))[0] is True
    assert allowed(t(2026, 11, 20, 12, 0))[0] is False

def test_saturday_23():
    assert allowed(t(2026, 11, 21, 22, 59))[0] is False
    assert allowed(t(2026, 11, 21, 23, 0))[0] is True

def test_chanukah_is_not_yomtov():
    assert allowed(t(2026, 12, 7, 10, 0))[0] is True

def test_pesach_2027():
    assert allowed(t(2027, 4, 21, 12, 30))[0] is False
    assert allowed(t(2027, 4, 22, 22, 0))[0] is False
    assert allowed(t(2027, 4, 22, 23, 0))[0] is True

def test_next_allowed_after_shabbat():
    assert next_allowed(t(2026, 11, 20, 13, 0)) == t(2026, 11, 21, 23, 0)

def test_utc_input_is_converted():
    from datetime import timezone
    # Friday 2026-11-20 10:30 UTC = 12:30 Israel
    assert allowed(datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc))[0] is False

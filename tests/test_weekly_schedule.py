from datetime import datetime
from zoneinfo import ZoneInfo

from shelfmate.flows.weekly import WHEN, next_sunday_nine


def at(*args):
    return datetime(*args, tzinfo=WHEN)


def test_later_in_the_week_goes_to_the_coming_sunday():
    # 2026-10-21 is a Wednesday
    assert next_sunday_nine(at(2026, 10, 21, 12)) == at(2026, 10, 25, 9)


def test_sunday_before_nine_is_today_and_after_nine_is_next_week():
    assert next_sunday_nine(at(2026, 10, 25, 8)) == at(2026, 10, 25, 9)
    assert next_sunday_nine(at(2026, 10, 25, 9)) == at(2026, 11, 1, 9)


def test_the_schedule_uses_india_time_not_utc():
    utc_now = datetime(2026, 10, 25, 3, 0, tzinfo=ZoneInfo("UTC"))  # 8:30am in India
    assert next_sunday_nine(utc_now.astimezone(WHEN)) == at(2026, 10, 25, 9)

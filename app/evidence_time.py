"""Capture intervals: a source date without timezone is not an exact instant."""
from datetime import date, datetime, time, timedelta, timezone


def capture_bounds(image):
    if image.get('captured_at'):
        instant = datetime.fromisoformat(image['captured_at'])
        return instant, instant
    day = date.fromisoformat(image['captured_on'])
    midnight = datetime.combine(day, time(), timezone.utc)
    # All civil offsets from UTC+14 through UTC-12; upper bound is exclusive.
    return midnight - timedelta(hours=14), midnight + timedelta(hours=36)


def capture_label(image):
    if image.get('captured_at'):
        return datetime.fromisoformat(image['captured_at']).isoformat()
    return f"{image['captured_on']}（仅日期，时区未知）"

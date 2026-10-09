"""
Time and deadline resolution utility for CountOn expectations.
Converts casual relative time phrases into timezone-aware UTC datetimes.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional


def parse_relative_deadline(
    deadline_str: Optional[str],
    reference_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Parses casual relative time phrases (e.g. 'today', 'tomorrow', 'this_week', 'next_month')
    or ISO-formatted strings into an aware UTC datetime.
    """
    if not deadline_str or not isinstance(deadline_str, str):
        return None

    cleaned = deadline_str.strip().lower().replace("-", "_").replace(" ", "_")
    if not cleaned:
        return None

    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # 1. Try standard ISO format
    try:
        iso_str = deadline_str.strip()
        parsed_dt = datetime.fromisoformat(iso_str)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt
    except (ValueError, TypeError):
        pass

    # 2. Specific named relative expressions
    if cleaned in ("today", "end_of_day"):
        return now.replace(hour=23, minute=59, second=59, microsecond=0)

    if cleaned in ("tomorrow",):
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)

    if cleaned in ("this_week", "end_of_week"):
        # End of current Sunday UTC
        days_to_sunday = (6 - now.weekday()) % 7
        target = now + timedelta(days=days_to_sunday)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)

    if cleaned in ("next_week",):
        # End of next Sunday UTC
        days_to_next_sunday = ((6 - now.weekday()) % 7) + 7
        target = now + timedelta(days=days_to_next_sunday)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)

    if cleaned in ("this_month", "end_of_month"):
        # Last day of current month
        if now.month == 12:
            next_month_first = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_first = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        last_day = next_month_first - timedelta(seconds=1)
        return last_day.replace(microsecond=0)

    if cleaned in ("next_month",):
        # Last day of next month
        year = now.year + 1 if now.month == 12 else now.year
        month = 1 if now.month == 12 else now.month + 1
        if month == 12:
            month_after_first = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_after_first = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        last_day = month_after_first - timedelta(seconds=1)
        return last_day.replace(microsecond=0)

    if cleaned in ("next_bill", "upcoming", "next_cycle"):
        # Default typical billing cycle: 30 days ahead at end of day
        target = now + timedelta(days=30)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)

    # 3. Numeric relative patterns: "in_3_days", "in_2_weeks", "in_5_hours"
    days_match = re.search(r"in_(\d+)_days?", cleaned)
    if days_match:
        n = int(days_match.group(1))
        target = now + timedelta(days=n)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)

    weeks_match = re.search(r"in_(\d+)_weeks?", cleaned)
    if weeks_match:
        n = int(weeks_match.group(1))
        target = now + timedelta(weeks=n)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)

    hours_match = re.search(r"in_(\d+)_hours?", cleaned)
    if hours_match:
        n = int(hours_match.group(1))
        return (now + timedelta(hours=n)).replace(microsecond=0)

    return None

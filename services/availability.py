"""
Slot generation logic.

Given a provider, a date, and a service duration, returns a list of available
datetime strings ('YYYY-MM-DD HH:MM') that are:
  - Inside at least one active availability_rule for that weekday
  - Not overlapping any blocked_window for that date
  - Not overlapping any pending or confirmed booking for that date
"""

from datetime import date, datetime, timedelta

from config import SLOT_INTERVAL_MINUTES
from db.database import (
    get_availability_rules,
    get_blocked_windows,
    get_busy_slots,
)


def _time_to_minutes(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _minutes_to_time(minutes: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """True if interval [start_a, end_a) overlaps [start_b, end_b)."""
    return start_a < end_b and end_a > start_b


def get_available_slots(provider_id: int, target_date: date, duration_minutes: int) -> list[str]:
    """
    Return list of 'YYYY-MM-DD HH:MM' strings representing available slot starts.

    A slot is available if:
    1. It fits within an active availability rule for target_date's weekday.
    2. It does not overlap any blocked window on target_date.
    3. It does not overlap any pending/confirmed booking on target_date.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday

    # 1. Build candidate windows from availability rules for this weekday
    rules = get_availability_rules(provider_id)
    work_windows: list[tuple[int, int]] = []
    for rule in rules:
        if rule["is_active"] and rule["day_of_week"] == day_of_week:
            work_windows.append(
                (_time_to_minutes(rule["start_time"]), _time_to_minutes(rule["end_time"]))
            )

    if not work_windows:
        return []

    # 2. Collect blocked windows for the date (as minute intervals)
    blocked = [
        (_time_to_minutes(bw["start_time"]), _time_to_minutes(bw["end_time"]))
        for bw in get_blocked_windows(provider_id, date_str)
    ]

    # 3. Collect busy slots from bookings (pending + confirmed)
    busy = []
    for slot in get_busy_slots(provider_id, date_str):
        dt = datetime.strptime(slot["requested_datetime"], "%Y-%m-%d %H:%M")
        start_min = dt.hour * 60 + dt.minute
        busy.append((start_min, start_min + slot["duration_minutes"]))

    # 4. Generate slots every SLOT_INTERVAL_MINUTES within each work window
    available: list[str] = []
    now = datetime.now()

    for work_start, work_end in work_windows:
        cursor = work_start
        while cursor + duration_minutes <= work_end:
            slot_start = cursor
            slot_end = cursor + duration_minutes

            # Skip if slot overlaps a blocked window
            if any(_overlaps(slot_start, slot_end, b_start, b_end) for b_start, b_end in blocked):
                cursor += SLOT_INTERVAL_MINUTES
                continue

            # Skip if slot overlaps a busy booking
            if any(_overlaps(slot_start, slot_end, b_start, b_end) for b_start, b_end in busy):
                cursor += SLOT_INTERVAL_MINUTES
                continue

            # Build full datetime and skip past slots
            slot_dt = datetime.combine(target_date, datetime.min.time()) + timedelta(minutes=slot_start)
            if slot_dt <= now:
                cursor += SLOT_INTERVAL_MINUTES
                continue

            available.append(f"{date_str} {_minutes_to_time(slot_start)}")
            cursor += SLOT_INTERVAL_MINUTES

    return available

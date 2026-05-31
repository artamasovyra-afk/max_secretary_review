from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Yekaterinburg"
DEFAULT_DEADLINE_HOUR = 18
DEFAULT_DEADLINE_MINUTE = 0
MIN_FUTURE_DEADLINE_DELTA = timedelta(minutes=1)
DEADLINE_MUST_BE_IN_FUTURE_DETAIL = "deadline_must_be_in_future"


@dataclass(frozen=True)
class DeadlineParseResult:
    deadline_at: datetime | None
    raw_text: str | None
    confidence: float
    matched_rule: str | None
    needs_clarification: bool


_WEEKDAYS = {
    "понедельник": 0,
    "понедельника": 0,
    "понедельнику": 0,
    "вторник": 1,
    "вторника": 1,
    "вторнику": 1,
    "среду": 2,
    "среда": 2,
    "среды": 2,
    "среде": 2,
    "четверг": 3,
    "четверга": 3,
    "четвергу": 3,
    "пятницу": 4,
    "пятница": 4,
    "пятницы": 4,
    "пятнице": 4,
    "субботу": 5,
    "суббота": 5,
    "субботы": 5,
    "субботе": 5,
    "воскресенье": 6,
    "воскресенья": 6,
    "воскресенью": 6,
}

_MONTHS = {
    "января": 1,
    "январь": 1,
    "февраля": 2,
    "февраль": 2,
    "марта": 3,
    "март": 3,
    "апреля": 4,
    "апрель": 4,
    "мая": 5,
    "май": 5,
    "июня": 6,
    "июнь": 6,
    "июля": 7,
    "июль": 7,
    "августа": 8,
    "август": 8,
    "сентября": 9,
    "сентябрь": 9,
    "октября": 10,
    "октябрь": 10,
    "ноября": 11,
    "ноябрь": 11,
    "декабря": 12,
    "декабрь": 12,
}

_RELATIVE_DELTA_PATTERN = (
    r"(?:через\s+полчаса|через\s+(?:(\d{1,4})\s+)?(минуту|минуты|минут|час|часа|часов))"
)
_RELATIVE_DELTA_RE = re.compile(rf"\b(?:сегодня\s+)?{_RELATIVE_DELTA_PATTERN}\b")
_FUTURE_DAY_WITH_RELATIVE_DELTA_RE = re.compile(rf"\b(?:завтра|послезавтра)\b.*\b{_RELATIVE_DELTA_PATTERN}\b")


def parse_deadline(text: str, now: datetime, timezone: str) -> DeadlineParseResult:
    normalized_text = _normalize_text(text)
    local_now = _to_local_now(now, timezone)

    if not normalized_text:
        return _not_found()

    if _FUTURE_DAY_WITH_RELATIVE_DELTA_RE.search(normalized_text):
        return _not_found()

    match = _RELATIVE_DELTA_RE.search(normalized_text)
    if match:
        amount_text = match.group(1)
        unit = match.group(2)
        if unit is None:
            delta = timedelta(minutes=30)
        else:
            amount = int(amount_text) if amount_text is not None else 1
            delta = timedelta(minutes=amount) if unit.startswith("минут") else timedelta(hours=amount)
        return _found(
            deadline_at=(local_now + delta).replace(microsecond=0),
            raw_text=match.group(0),
            matched_rule="relative_delta",
            confidence=0.95,
        )

    match = re.search(
        r"\b(сегодня|завтра|послезавтра)\b(?:\s+(?:в|до|к)?\s*(\d{1,2}):(\d{2}))?",
        normalized_text,
    )
    if match:
        day_offsets = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
        day = local_now.date() + timedelta(days=day_offsets[match.group(1)])
        hour, minute = _time_from_match(match.group(2), match.group(3))
        return _found(
            deadline_at=_combine_local(day, local_now, hour, minute),
            raw_text=match.group(0),
            matched_rule=f"relative_day_{match.group(1)}",
            confidence=0.95,
        )

    match = re.search(r"\b(?:до\s+вечера|до\s+конца\s+дня)\b", normalized_text)
    if match:
        return _found(
            deadline_at=_combine_default_time(local_now.date(), local_now),
            raw_text=match.group(0),
            matched_rule="end_of_day",
            confidence=0.9,
        )

    match = re.search(r"\b(?:до|к)\s+(" + "|".join(_WEEKDAYS) + r")\b", normalized_text)
    if match:
        target_weekday = _WEEKDAYS[match.group(1)]
        days_ahead = (target_weekday - local_now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return _found(
            deadline_at=_combine_default_time(local_now.date() + timedelta(days=days_ahead), local_now),
            raw_text=match.group(0),
            matched_rule="weekday",
            confidence=0.9,
        )

    match = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", normalized_text)
    if match:
        deadline = _date_from_numeric_match(match, local_now)
        if deadline is not None:
            return _found(
                deadline_at=deadline,
                raw_text=match.group(0),
                matched_rule="numeric_date",
                confidence=0.9,
            )

    match = re.search(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\b", normalized_text)
    if match:
        deadline = _date_from_month_name_match(match, local_now)
        if deadline is not None:
            return _found(
                deadline_at=deadline,
                raw_text=match.group(0),
                matched_rule="month_name_date",
                confidence=0.9,
            )

    match = re.search(r"\b(?:в|до|к)\s+(\d{1,2}):(\d{2})\b", normalized_text)
    if match:
        hour, minute = _time_from_match(match.group(1), match.group(2))
        deadline = _combine_local(local_now.date(), local_now, hour, minute)
        if deadline <= local_now:
            deadline = _combine_local(local_now.date() + timedelta(days=1), local_now, hour, minute)
        return _found(
            deadline_at=deadline,
            raw_text=match.group(0),
            matched_rule="time_only",
            confidence=0.8,
        )

    return _not_found()


def local_day_bounds_utc(
    now: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> tuple[datetime, datetime]:
    local_now = _to_local_now(now, timezone_name)
    local_start = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=local_now.tzinfo)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_future_task_deadline(
    value: datetime | None,
    *,
    now: datetime | None = None,
    min_delta: timedelta = MIN_FUTURE_DEADLINE_DELTA,
) -> bool:
    if value is None:
        return True
    deadline_at = as_aware_utc(value)
    if deadline_at is None:
        return True
    now_utc = as_aware_utc(now or datetime.now(timezone.utc))
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    return deadline_at >= now_utc + min_delta


def _normalize_text(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split())


def _to_local_now(now: datetime, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def _time_from_match(hour_text: str | None, minute_text: str | None) -> tuple[int, int]:
    if hour_text is None or minute_text is None:
        return DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE
    hour = int(hour_text)
    minute = int(minute_text)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE
    return hour, minute


def _combine_default_time(day: object, local_now: datetime) -> datetime:
    return _combine_local(day, local_now, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE)


def _combine_local(day: object, local_now: datetime, hour: int, minute: int) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=local_now.tzinfo).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def _date_from_numeric_match(match: re.Match[str], local_now: datetime) -> datetime | None:
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) is not None else local_now.year
    return _date_with_default_time(day=day, month=month, year=year, local_now=local_now, roll_year=match.group(3) is None)


def _date_from_month_name_match(match: re.Match[str], local_now: datetime) -> datetime | None:
    day = int(match.group(1))
    month = _MONTHS[match.group(2)]
    return _date_with_default_time(day=day, month=month, year=local_now.year, local_now=local_now, roll_year=True)


def _date_with_default_time(
    *,
    day: int,
    month: int,
    year: int,
    local_now: datetime,
    roll_year: bool,
) -> datetime | None:
    try:
        deadline = _combine_default_time(datetime(year, month, day).date(), local_now)
    except ValueError:
        return None
    if roll_year and deadline < local_now:
        try:
            deadline = _combine_default_time(datetime(year + 1, month, day).date(), local_now)
        except ValueError:
            return None
    return deadline


def _found(
    *,
    deadline_at: datetime,
    raw_text: str,
    matched_rule: str,
    confidence: float,
) -> DeadlineParseResult:
    return DeadlineParseResult(
        deadline_at=deadline_at,
        raw_text=raw_text,
        confidence=confidence,
        matched_rule=matched_rule,
        needs_clarification=False,
    )


def _not_found() -> DeadlineParseResult:
    return DeadlineParseResult(
        deadline_at=None,
        raw_text=None,
        confidence=0.0,
        matched_rule=None,
        needs_clarification=True,
    )

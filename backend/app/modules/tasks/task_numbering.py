from __future__ import annotations

import re

TASK_REF_PATTERN = re.compile(r"^\s*(?:#|[Tt]-)?(?P<number>\d+)\s*$")


def normalize_task_ref(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None

    match = TASK_REF_PATTERN.match(value)
    if match is None:
        return None

    task_number = int(match.group("number"))
    return task_number if task_number > 0 else None


def format_task_ref(task_number: int) -> str:
    return f"#{task_number}"

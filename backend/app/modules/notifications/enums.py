from __future__ import annotations

from enum import Enum


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DM_UNAVAILABLE = "dm_unavailable"
    SKIPPED = "skipped"

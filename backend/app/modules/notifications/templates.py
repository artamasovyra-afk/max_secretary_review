from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.bot.callbacks import build_callback_payload

DEFAULT_NOTIFICATION_TIMEZONE = "Europe/Moscow"


class PersonalNotificationTemplate(str, Enum):
    NEW_TASK = "new_task"
    DEADLINE_SOON = "deadline_soon"
    DEADLINE_EXPIRED = "deadline_expired"
    REPORT_EXPECTED = "report_expected"
    RESPONSE_WAITING_ACCEPTANCE = "response_waiting_acceptance"


@dataclass(frozen=True)
class AbstractNotificationButton:
    label: str
    payload: str


@dataclass(frozen=True)
class PersonalTaskNotification:
    template: PersonalNotificationTemplate
    title: str
    message: str
    buttons: tuple[AbstractNotificationButton, ...]


_TEMPLATE_TITLES: dict[PersonalNotificationTemplate, str] = {
    PersonalNotificationTemplate.NEW_TASK: "Новая задача",
    PersonalNotificationTemplate.DEADLINE_SOON: "Срок скоро",
    PersonalNotificationTemplate.DEADLINE_EXPIRED: "Срок истек",
    PersonalNotificationTemplate.REPORT_EXPECTED: "Ожидается отчет",
    PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE: "Ответ ожидает приемки",
}

_TEMPLATE_LEADS: dict[PersonalNotificationTemplate, str] = {
    PersonalNotificationTemplate.NEW_TASK: "Вам назначена задача.",
    PersonalNotificationTemplate.DEADLINE_SOON: "Срок по задаче скоро истечет.",
    PersonalNotificationTemplate.DEADLINE_EXPIRED: "Срок по задаче истек.",
    PersonalNotificationTemplate.REPORT_EXPECTED: "По задаче ожидается ваш отчет.",
    PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE: "Ответ по задаче ожидает приемки.",
}


def build_personal_task_notification(
    *,
    template: PersonalNotificationTemplate,
    task_id: UUID,
    task_title: str,
    deadline_at: datetime | None,
    creator_display_name: str | None,
    group_title: str | None,
    task_number: int | None = None,
    response_id: UUID | None = None,
    assignee_display_name: str | None = None,
    timezone_name: str = DEFAULT_NOTIFICATION_TIMEZONE,
) -> PersonalTaskNotification:
    if template == PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE:
        return _build_waiting_acceptance_notification(
            task_id=task_id,
            task_number=task_number,
            task_title=task_title,
            deadline_at=deadline_at,
            response_id=response_id,
            assignee_display_name=assignee_display_name,
            timezone_name=timezone_name,
        )

    buttons = build_default_task_buttons(task_id)
    title = _TEMPLATE_TITLES[template]
    message = "\n".join(
        [
            title,
            "",
            _TEMPLATE_LEADS[template],
            "",
            f"Задача: {task_title}",
            f"Срок: {_format_deadline(deadline_at, timezone_name)}",
            f"Постановщик: {_fallback_text(creator_display_name, 'Не указан')}",
            f"Группа: {_fallback_text(group_title, 'Не указана')}",
            "",
            "Действия:",
            *[f"[{button.label}] payload={button.payload}" for button in buttons],
        ]
    )
    return PersonalTaskNotification(
        template=template,
        title=title,
        message=message,
        buttons=buttons,
    )


def build_acceptance_task_buttons(
    task_id: UUID,
    *,
    response_id: UUID | None,
) -> tuple[AbstractNotificationButton, ...]:
    buttons: list[AbstractNotificationButton] = []
    if response_id is not None:
        buttons.extend(
            [
                AbstractNotificationButton(
                    label="Принять",
                    payload=build_callback_payload("accept", task_id, response_id=response_id),
                ),
                AbstractNotificationButton(
                    label="Отклонить",
                    payload=build_callback_payload("reject", task_id, response_id=response_id),
                ),
            ]
        )
    buttons.append(
        AbstractNotificationButton(
            label="Открыть задачу",
            payload=build_callback_payload("open", task_id),
        )
    )
    return tuple(buttons)


def build_default_task_buttons(task_id: UUID) -> tuple[AbstractNotificationButton, ...]:
    return (
        AbstractNotificationButton(
            label="В работу",
            payload=build_callback_payload("start", task_id),
        ),
        AbstractNotificationButton(
            label="Ответить",
            payload=build_callback_payload("reply", task_id),
        ),
        AbstractNotificationButton(
            label="Отложить",
            payload=build_callback_payload("snooze", task_id, snooze="1h"),
        ),
        AbstractNotificationButton(
            label="Открыть задачу",
            payload=build_callback_payload("open", task_id),
        ),
    )


def _build_waiting_acceptance_notification(
    *,
    task_id: UUID,
    task_number: int | None,
    task_title: str,
    deadline_at: datetime | None,
    response_id: UUID | None,
    assignee_display_name: str | None,
    timezone_name: str,
) -> PersonalTaskNotification:
    title = _TEMPLATE_TITLES[PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE]
    task_ref = f"#{task_number}" if task_number is not None else ""
    task_line = f"Задача {task_ref}".strip()
    buttons = build_acceptance_task_buttons(task_id, response_id=response_id)
    message = "\n".join(
        [
            "Ответ ожидает приемки ✅",
            "",
            task_line,
            f"Текст: {task_title}",
            f"Исполнитель: {_fallback_text(assignee_display_name, 'Не указан')}",
            f"Срок: {_format_deadline(deadline_at, timezone_name)}",
            "",
            "Исполнитель отправил отчет. Примите или отклоните результат.",
        ]
    )
    return PersonalTaskNotification(
        template=PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE,
        title=title,
        message=message,
        buttons=buttons,
    )


def _format_deadline(deadline_at: datetime | None, timezone_name: str) -> str:
    if deadline_at is None:
        return "Без срока"

    value = deadline_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc

    return value.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def _fallback_text(value: str | None, fallback: str) -> str:
    if value is None or not value.strip():
        return fallback
    return value.strip()

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.modules.notifications.templates import (
    AbstractNotificationButton,
    PersonalNotificationTemplate,
    build_default_task_buttons,
    build_personal_task_notification,
)

TASK_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_new_task_notification_snapshot() -> None:
    notification = build_personal_task_notification(
        template=PersonalNotificationTemplate.NEW_TASK,
        task_id=TASK_ID,
        task_title="Подготовить отчет",
        deadline_at=datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc),
        creator_display_name="Иван Петров",
        group_title="Отдел продаж",
        timezone_name="UTC",
    )

    assert notification.title == "Новая задача"
    assert notification.message == (
        "Новая задача\n"
        "\n"
        "Вам назначена задача.\n"
        "\n"
        "Задача: Подготовить отчет\n"
        "Срок: 25.05.2026 15:00\n"
        "Постановщик: Иван Петров\n"
        "Группа: Отдел продаж\n"
        "\n"
        "Действия:\n"
        "[В работу] payload=task:start:11111111-1111-4111-8111-111111111111\n"
        "[Ответить] payload=task:reply:11111111-1111-4111-8111-111111111111\n"
        "[Отложить] payload=task:snooze:1h:11111111-1111-4111-8111-111111111111\n"
        "[Открыть задачу] payload=task:open:11111111-1111-4111-8111-111111111111"
    )
    assert notification.buttons == (
        AbstractNotificationButton(
            label="В работу",
            payload="task:start:11111111-1111-4111-8111-111111111111",
        ),
        AbstractNotificationButton(
            label="Ответить",
            payload="task:reply:11111111-1111-4111-8111-111111111111",
        ),
        AbstractNotificationButton(
            label="Отложить",
            payload="task:snooze:1h:11111111-1111-4111-8111-111111111111",
        ),
        AbstractNotificationButton(
            label="Открыть задачу",
            payload="task:open:11111111-1111-4111-8111-111111111111",
        ),
    )


@pytest.mark.parametrize(
    ("template", "expected_title", "expected_lead"),
    [
        (
            PersonalNotificationTemplate.DEADLINE_SOON,
            "Срок скоро",
            "Срок по задаче скоро истечет.",
        ),
        (
            PersonalNotificationTemplate.DEADLINE_EXPIRED,
            "Срок истек",
            "Срок по задаче истек.",
        ),
        (
            PersonalNotificationTemplate.REPORT_EXPECTED,
            "Ожидается отчет",
            "По задаче ожидается ваш отчет.",
        ),
    ],
)
def test_all_personal_notification_templates_include_required_context(
    template: PersonalNotificationTemplate,
    expected_title: str,
    expected_lead: str,
) -> None:
    notification = build_personal_task_notification(
        template=template,
        task_id=TASK_ID,
        task_title="Проверить доступ",
        deadline_at=None,
        creator_display_name="Мария",
        group_title="Проектный чат",
        timezone_name="UTC",
    )

    assert notification.title == expected_title
    assert expected_lead in notification.message
    assert "Задача: Проверить доступ" in notification.message
    assert "Срок: Без срока" in notification.message
    assert "Постановщик: Мария" in notification.message
    assert "Группа: Проектный чат" in notification.message
    assert [button.label for button in notification.buttons] == [
        "В работу",
        "Ответить",
        "Отложить",
        "Открыть задачу",
    ]
    assert all(button.payload.startswith("task:") for button in notification.buttons)


def test_waiting_acceptance_notification_is_clean_and_actionable() -> None:
    response_id = UUID("22222222-2222-4222-8222-222222222222")
    notification = build_personal_task_notification(
        template=PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE,
        task_id=TASK_ID,
        task_number=123,
        response_id=response_id,
        task_title="Подготовить отчет",
        deadline_at=datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc),
        creator_display_name="Мария",
        group_title="Проектный чат",
        assignee_display_name="Иван Иванов",
        timezone_name="UTC",
    )

    assert notification.message == (
        "Ответ ожидает приемки ✅\n"
        "\n"
        "Задача #123\n"
        "Текст: Подготовить отчет\n"
        "Исполнитель: Иван Иванов\n"
        "Срок: 25.05.2026 15:00\n"
        "\n"
        "Исполнитель отправил отчет. Примите или отклоните результат."
    )
    assert "payload=" not in notification.message
    assert "Пользователь #" not in notification.message
    assert "Группа #" not in notification.message
    assert [button.label for button in notification.buttons] == ["Принять", "Отклонить", "Открыть задачу"]
    assert notification.buttons[0].payload == (
        "task:accept:11111111-1111-4111-8111-111111111111:22222222-2222-4222-8222-222222222222"
    )
    assert notification.buttons[1].payload == (
        "task:reject:11111111-1111-4111-8111-111111111111:22222222-2222-4222-8222-222222222222"
    )
    assert notification.buttons[2].payload == "task:open:11111111-1111-4111-8111-111111111111"


def test_notification_template_uses_safe_fallback_labels() -> None:
    notification = build_personal_task_notification(
        template=PersonalNotificationTemplate.DEADLINE_SOON,
        task_id=TASK_ID,
        task_title="Задача без контекста",
        deadline_at=None,
        creator_display_name=" ",
        group_title=None,
    )

    assert "Постановщик: Не указан" in notification.message
    assert "Группа: Не указана" in notification.message


def test_default_task_buttons_are_abstract_callback_payloads() -> None:
    buttons = build_default_task_buttons(TASK_ID)

    assert [button.label for button in buttons] == [
        "В работу",
        "Ответить",
        "Отложить",
        "Открыть задачу",
    ]
    assert [button.payload for button in buttons] == [
        "task:start:11111111-1111-4111-8111-111111111111",
        "task:reply:11111111-1111-4111-8111-111111111111",
        "task:snooze:1h:11111111-1111-4111-8111-111111111111",
        "task:open:11111111-1111-4111-8111-111111111111",
    ]

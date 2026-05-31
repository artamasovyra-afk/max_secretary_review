from app.modules.integrations.enums import (
    BitrixSyncStatus,
    BitrixUserMatchSource,
    IntegrationAuthType,
    IntegrationProvider,
)


def enum_values(enum_type) -> list[str]:
    return [item.value for item in enum_type]


def test_integration_provider_values() -> None:
    assert enum_values(IntegrationProvider) == [
        "bitrix24",
        "max",
        "openai",
        "yandexgpt",
        "gigachat",
    ]


def test_integration_auth_type_values() -> None:
    assert enum_values(IntegrationAuthType) == [
        "webhook",
        "oauth",
        "token",
        "none",
    ]


def test_bitrix_sync_status_values() -> None:
    assert enum_values(BitrixSyncStatus) == [
        "pending",
        "synced",
        "error",
        "disabled",
    ]


def test_bitrix_user_match_source_values() -> None:
    assert enum_values(BitrixUserMatchSource) == [
        "manual",
        "email",
        "phone",
        "import",
    ]

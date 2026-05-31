from enum import Enum


class IntegrationProvider(str, Enum):
    BITRIX24 = "bitrix24"
    MAX = "max"
    OPENAI = "openai"
    YANDEXGPT = "yandexgpt"
    GIGACHAT = "gigachat"


class IntegrationAuthType(str, Enum):
    WEBHOOK = "webhook"
    OAUTH = "oauth"
    TOKEN = "token"
    NONE = "none"


class BitrixSyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    ERROR = "error"
    DISABLED = "disabled"


class BitrixUserMatchSource(str, Enum):
    MANUAL = "manual"
    EMAIL = "email"
    PHONE = "phone"
    IMPORT = "import"

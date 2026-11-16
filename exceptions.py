from typing import Any, Optional


class PlatformBaseError(Exception):
    """Базовое исключение платформы AI PicChanger+SEO."""

    def __init__(
        self,
        message: str,
        code: str = "PLATFORM_ERROR",
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class AIProviderNetworkError(PlatformBaseError):
    """Сетевой сбой или таймаут при обращении к шлюзу ИИ."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, code="AI_PROVIDER_NETWORK_ERROR", status_code=502, details=details)


class AIContentValidationError(PlatformBaseError):
    """Ответ нейросети не прошел валидацию схемы или качества."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, code="AI_CONTENT_VALIDATION_ERROR", status_code=422, details=details)


class InvalidMediaError(PlatformBaseError):
    """Поврежденный, неподдерживаемый или нечитаемый медиафайл."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, code="INVALID_MEDIA_ERROR", status_code=400, details=details)


class CMSConnectorError(PlatformBaseError):
    """Ошибка взаимодействия с внешней CMS или маркетплейсом."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, code="CMS_CONNECTOR_ERROR", status_code=502, details=details)


class BudgetLimitExceededError(PlatformBaseError):
    """Превышен дневной или пакетный финансовый лимит операций."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, code="BUDGET_LIMIT_EXCEEDED", status_code=402, details=details)


class InvalidFSMTransitionError(PlatformBaseError):
    """Попытка недопустимого перехода между статусами конечного автомата."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, code="INVALID_FSM_TRANSITION", status_code=409, details=details)

from core.config import AppMode, get_settings
from core.exceptions import PlatformBaseError
from agents.providers.base_provider import AIProviderAdapter
from agents.providers.mock_provider import MockAIProvider


def get_ai_provider() -> AIProviderAdapter:
    """Возвращает активный адаптер нейросетей строго согласно APP_MODE."""
    settings = get_settings()
    if settings.app_mode == AppMode.DEV_MOCK:
        return MockAIProvider()
    if settings.app_mode == AppMode.CLOUD_API:
        raise PlatformBaseError(
            "CLOUD_API provider adapter is scheduled for Session 4",
            code="PROVIDER_NOT_IMPLEMENTED",
            status_code=501,
        )
    if settings.app_mode == AppMode.GPU_SERVER:
        raise PlatformBaseError(
            "GPU_SERVER provider adapter is scheduled for Session 4",
            code="PROVIDER_NOT_IMPLEMENTED",
            status_code=501,
        )
    return MockAIProvider()

from core.config import AppMode, get_settings
from agents.providers.base_provider import AIProviderAdapter
from agents.providers.cloud_provider import CloudAPIProvider
from agents.providers.gpu_server_provider import GPUServerProvider
from agents.providers.mock_provider import MockAIProvider


def get_ai_provider() -> AIProviderAdapter:
    """Возвращает активный адаптер нейросетей строго согласно APP_MODE."""
    settings = get_settings()
    if settings.app_mode == AppMode.DEV_MOCK:
        return MockAIProvider()
    if settings.app_mode == AppMode.CLOUD_API:
        return CloudAPIProvider()
    if settings.app_mode == AppMode.GPU_SERVER:
        return GPUServerProvider()
    return MockAIProvider()

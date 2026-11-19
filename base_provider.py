from abc import ABC, abstractmethod
from typing import Any


class AIProviderAdapter(ABC):
    """Единый интерфейс паттерна «Стратегия» для всех контуров ИИ."""

    provider_name: str = "base"

    @abstractmethod
    async def analyze_product(
        self,
        product_id: str,
        title: str,
        image_url: str,
        enable_vision: bool = True,
        lang: str = "ru",
    ) -> dict[str, Any]:
        """VLM-анализ исходного изображения, определение BBox и ключевых свойств."""

    @abstractmethod
    async def build_funnel_and_seo(
        self,
        product_id: str,
        title: str,
        attributes: dict[str, Any],
        slides_count: int = 5,
        lang: str = "ru",
    ) -> dict[str, Any]:
        """Генерация 5-слайдовой продающей матрицы, изолированного рич-контента и SEO."""

    @abstractmethod
    async def generate_background(
        self,
        product_id: str,
        style_archetype: str,
        mode: str = "studio",
        bbox: list[float] | None = None,
    ) -> dict[str, Any]:
        """Генерация чистого фонового слоя (растр) с учетом безопасной зоны под текст."""

    @abstractmethod
    async def validate_slide(
        self,
        product_id: str,
        slide_index: int,
        layout_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Vision-аудит слайда на артефакты, перекрытие товара и читаемость."""

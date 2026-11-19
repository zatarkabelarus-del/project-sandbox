from typing import Any
from agents.providers.base_provider import AIProviderAdapter
from core.i18n import load_seo_templates


class MockAIProvider(AIProviderAdapter):
    """Мгновенный детерминированный провайдер для контура DEV_MOCK (0.00 USD)."""

    provider_name = "DEV_MOCK_PROVIDER"

    async def analyze_product(
        self,
        product_id: str,
        title: str,
        image_url: str,
        enable_vision: bool = True,
        lang: str = "ru",
    ) -> dict[str, Any]:
        return {
            "product_id": product_id,
            "vision_enabled": enable_vision,
            "detected_bbox": [0.22, 0.18, 0.56, 0.64],
            "dominant_colors": ["#1E293B", "#F8FAFC", "#2563EB"],
            "visual_summary": (
                f"Центральный объект '{title}' с четким контуром и свободным пространством под инфографику."
                if lang == "ru"
                else f"Centered subject '{title}' with clean silhouette and safe negative space for callouts."
            ),
            "estimated_cost_usd": 0.0,
        }

    async def build_funnel_and_seo(
        self,
        product_id: str,
        title: str,
        attributes: dict[str, Any],
        slides_count: int = 5,
        lang: str = "ru",
    ) -> dict[str, Any]:
        templates = load_seo_templates()["product"].get(lang, load_seo_templates()["product"]["ru"])
        slug_base = product_id.lower().replace("_", "-")

        slides_roles_ru = [
            ("Главный оффер", "Высокая надежность и точное соответствие стандартам"),
            ("Ключевое преимущество", "Увеличенный ресурс работы в интенсивном режиме"),
            ("Технические параметры", "Проверенные материалы и контроль качества"),
            ("Комплектация и монтаж", "Полная готовность к быстрой установке"),
            ("Гарантия и сервис", "Официальная поддержка и безопасная упаковка"),
        ]
        slides_roles_en = [
            ("Main Offer", "High reliability and strict compliance with standards"),
            ("Key Advantage", "Extended service life under intensive load"),
            ("Technical Specs", "Verified materials and multi-stage quality control"),
            ("Package & Setup", "Ready for quick and hassle-free installation"),
            ("Warranty & Support", "Official warranty and protective packaging"),
        ]
        roles = slides_roles_ru if lang == "ru" else slides_roles_en

        slides = []
        for idx in range(1, slides_count + 1):
            role_title, usp_text = roles[(idx - 1) % len(roles)]
            slides.append(
                {
                    "slide_index": idx,
                    "role": role_title,
                    "headline": f"{title} — {role_title}",
                    "subheadline": usp_text,
                    "alt_text": templates["image_alt"].format(
                        product_name=title,
                        slide_index=idx,
                        usp_short=role_title,
                    ),
                    "file_slug": templates["image_slug"].format(slug=slug_base, slide_index=idx),
                }
            )

        rich_html = (
            f'<div class="ai-rich-content" data-product-id="{product_id}">'
            f"<h3>{title}</h3>"
            f"<ul>{''.join(f'<li><strong>{s['role']}:</strong> {s['subheadline']}</li>' for s in slides)}</ul>"
            f"</div>"
        )

        return {
            "product_id": product_id,
            "slides": slides,
            "rich_content_html": rich_html,
            "seo": {
                "meta_title": templates["meta_title"].format(product_name=title),
                "meta_description": templates["meta_description"].format(
                    product_name=title,
                    brand_or_type=attributes.get("category", "e-commerce"),
                ),
            },
            "estimated_cost_usd": 0.0,
        }

    async def generate_background(
        self,
        product_id: str,
        style_archetype: str,
        mode: str = "studio",
        bbox: list[float] | None = None,
    ) -> dict[str, Any]:
        return {
            "product_id": product_id,
            "style_archetype": style_archetype,
            "generation_mode": mode,
            "background_layer_url": f"/mock-assets/{product_id}/bg_{style_archetype}_{mode}.webp",
            "safe_zones": [
                {"zone": "top_left", "x": 0.05, "y": 0.05, "w": 0.42, "h": 0.16},
                {"zone": "bottom_left", "x": 0.05, "y": 0.78, "w": 0.90, "h": 0.16},
            ],
            "estimated_cost_usd": 0.0,
        }

    async def validate_slide(
        self,
        product_id: str,
        slide_index: int,
        layout_schema: dict[str, Any],
    ) -> dict[str, Any]:
        layers = layout_schema.get("layers", [])
        return {
            "product_id": product_id,
            "slide_index": slide_index,
            "passed": True,
            "score": 0.98,
            "checked_layers_count": len(layers),
            "issues": [],
            "estimated_cost_usd": 0.0,
        }

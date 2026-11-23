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
        avoid_title_duplication: bool = False,
        lang: str = "ru",
    ) -> dict[str, Any]:
        templates = load_seo_templates()["product"].get(lang, load_seo_templates()["product"]["ru"])
        slug_base = product_id.lower().replace("_", "-")
        safe_count = max(1, min(8, int(slides_count)))

        role_catalog_ru: dict[str, tuple[str, str, str]] = {
            "cover_main_offer": (
                "Главный оффер",
                "Максимальный ресурс и надёжность",
                "Высокая надежность и точное соответствие стандартам",
            ),
            "specs_and_numbers": (
                "Технические параметры",
                "Точная геометрия и проверенные материалы",
                "Проверенные материалы и многоступенчатый контроль качества",
            ),
            "details_pain_solver": (
                "Ключевое преимущество",
                "Устойчивость к интенсивным нагрузкам",
                "Увеличенный ресурс работы в интенсивном режиме эксплуатации",
            ),
            "usage_lifestyle": (
                "Сценарий применения",
                "Удобство в ежедневной работе",
                "Продуманная эргономика и стабильная работа без перегрева",
            ),
            "trust_and_guarantee": (
                "Гарантия и сервис",
                "Официальная гарантия качества",
                "Официальная поддержка, контроль партии и защитная упаковка",
            ),
            "compatibility_and_fit": (
                "Совместимость и посадка",
                "100% соответствие посадочным размерам",
                "Точная совместимость со штатными узлами без доработок",
            ),
            "package_contents": (
                "Комплектация поставки",
                "Всё необходимое в заводском комплекте",
                "Полная готовность к быстрой установке сразу из коробки",
            ),
            "faq_and_care": (
                "Ресурс и обслуживание",
                "Простое обслуживание и долгий срок службы",
                "Рекомендации по эксплуатации для максимального ресурса узла",
            ),
        }

        role_catalog_en: dict[str, tuple[str, str, str]] = {
            "cover_main_offer": (
                "Main Offer",
                "Maximum Durability & Precision",
                "High reliability and strict compliance with standards",
            ),
            "specs_and_numbers": (
                "Technical Specs",
                "Precision Geometry & Tested Alloys",
                "Verified materials and multi-stage quality control",
            ),
            "details_pain_solver": (
                "Key Advantage",
                "Built for Heavy-Duty Loads",
                "Extended service life under intensive operating loads",
            ),
            "usage_lifestyle": (
                "Usage Scenario",
                "Effortless Everyday Performance",
                "Ergonomic design and stable performance in real conditions",
            ),
            "trust_and_guarantee": (
                "Warranty & Support",
                "Official Warranty & Protection",
                "Official warranty, batch inspection, and protective packaging",
            ),
            "compatibility_and_fit": (
                "Compatibility & Fit",
                "100% OEM Fitment Accuracy",
                "Direct drop-in compatibility with zero modifications required",
            ),
            "package_contents": (
                "Package Contents",
                "Complete Ready-to-Install Kit",
                "Everything included in factory-sealed packaging",
            ),
            "faq_and_care": (
                "Care & Longevity",
                "Easy Maintenance & Long Lifespan",
                "Practical care guidelines to maximize service intervals",
            ),
        }

        matrices: dict[int, list[str]] = {
            1: ["cover_main_offer"],
            2: ["cover_main_offer", "specs_and_numbers"],
            3: ["cover_main_offer", "specs_and_numbers", "trust_and_guarantee"],
            4: ["cover_main_offer", "specs_and_numbers", "details_pain_solver", "trust_and_guarantee"],
            5: ["cover_main_offer", "specs_and_numbers", "details_pain_solver", "usage_lifestyle", "trust_and_guarantee"],
            6: ["cover_main_offer", "specs_and_numbers", "details_pain_solver", "usage_lifestyle", "compatibility_and_fit", "trust_and_guarantee"],
            7: ["cover_main_offer", "specs_and_numbers", "details_pain_solver", "usage_lifestyle", "compatibility_and_fit", "package_contents", "trust_and_guarantee"],
            8: ["cover_main_offer", "specs_and_numbers", "details_pain_solver", "usage_lifestyle", "compatibility_and_fit", "package_contents", "faq_and_care", "trust_and_guarantee"],
        }

        catalog = role_catalog_ru if lang == "ru" else role_catalog_en
        chosen_codes = matrices[safe_count]

        slides = []
        for idx, code in enumerate(chosen_codes, start=1):
            role_title, hook_headline, usp_text = catalog[code]
            headline_text = hook_headline if avoid_title_duplication else f"{title} — {role_title}"
            slides.append(
                {
                    "slide_index": idx,
                    "role": role_title,
                    "role_code": code,
                    "headline": headline_text,
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
            "slides_count": safe_count,
            "avoid_title_duplication": avoid_title_duplication,
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
        image_model: str | None = None,
        environment_hint: str = ""
    ) -> dict[str, Any]:
        selected_model = (image_model or "nanobanana-flash").strip()
        return {
            "product_id": product_id,
            "style_archetype": style_archetype,
            "generation_mode": mode,
            "image_model": selected_model,
            "background_layer_url": f"/mock-assets/{product_id}/bg_{selected_model}_{style_archetype}_{mode}.webp",
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

import json
from typing import Any
from agents.providers.factory import get_ai_provider
from core.config import CONFIGS_DIR


class MarketerAgent:
    """Агент 2: Маркетолог-сценарист (воронка 5 слайдов без дублей + SEO + изолированный рич-контент)."""

    def __init__(self) -> None:
        prompts_path = CONFIGS_DIR / "prompts" / "agents_prompts.json"
        with prompts_path.open("r", encoding="utf-8") as f:
            self.config = json.load(f).get("marketer", {})

    async def build_funnel_and_seo(
        self,
        product_id: str,
        title: str,
        attributes: dict[str, Any],
        vision_brief: dict[str, Any] | None = None,
        slides_count: int = 5,
        lang: str = "ru",
    ) -> dict[str, Any]:
        provider = get_ai_provider()
        enriched_attrs = dict(attributes)
        if vision_brief and vision_brief.get("vision_enabled"):
            enriched_attrs["_visual_context"] = vision_brief.get("visual_summary", "")

        result = await provider.build_funnel_and_seo(
            product_id=product_id,
            title=title,
            attributes=enriched_attrs,
            slides_count=slides_count,
            lang=lang,
        )

        matrix = self.config.get("slide_roles", [])
        for idx, slide in enumerate(result.get("slides", [])):
            if idx < len(matrix):
                slide["role_code"] = matrix[idx]["role"]

        raw_html = result.get("rich_content_html", "")
        if "ai-picchanger-rich-isolated" not in raw_html:
            result["rich_content_html"] = (
                f'<section class="ai-picchanger-rich-isolated" style="all:initial;display:block;font-family:sans-serif;">'
                f"{raw_html}</section>"
            )
        return result

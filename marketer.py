import json
from typing import Any
from agents.providers.factory import get_ai_provider
from core.config import CONFIGS_DIR


class MarketerAgent:
    """Агент 2: Маркетолог-сценарист (воронка 1..8 слайдов без дублей + SEO + изолированный рич-контент)."""

    def __init__(self) -> None:
        prompts_path = CONFIGS_DIR / "prompts" / "agents_prompts.json"
        with prompts_path.open("r", encoding="utf-8") as f:
            self.config = json.load(f).get("marketer", {})

    def _resolve_role_sequence(self, slides_count: int) -> list[str]:
        safe_count = max(1, min(8, int(slides_count)))
        matrices = self.config.get("funnel_matrices", {})
        if str(safe_count) in matrices and isinstance(matrices[str(safe_count)], list):
            return [str(r) for r in matrices[str(safe_count)]]
        all_roles = [str(item.get("role", "feature")) for item in self.config.get("slide_roles", [])]
        return all_roles[:safe_count]

    @staticmethod
    def _strip_duplicated_title(headline: str, product_title: str, fallback_role: str) -> str:
        clean_title = product_title.strip()
        if not clean_title:
            return headline
        lower_head = headline.lower()
        lower_title = clean_title.lower()
        if lower_title in lower_head:
            idx = lower_head.find(lower_title)
            stripped = (headline[:idx] + headline[idx + len(clean_title):]).strip(" —-:|,.")
            return stripped if stripped else fallback_role
        return headline

    async def build_funnel_and_seo(
        self,
        product_id: str,
        title: str,
        attributes: dict[str, Any],
        vision_brief: dict[str, Any] | None = None,
        slides_count: int = 5,
        avoid_title_duplication: bool = False,
        lang: str = "ru",
    ) -> dict[str, Any]:
        provider = get_ai_provider()
        safe_count = max(1, min(8, int(slides_count)))
        enriched_attrs = dict(attributes)
        if vision_brief and vision_brief.get("vision_enabled"):
            enriched_attrs["_visual_context"] = vision_brief.get("visual_summary", "")

        result = await provider.build_funnel_and_seo(
            product_id=product_id,
            title=title,
            attributes=enriched_attrs,
            slides_count=safe_count,
            avoid_title_duplication=avoid_title_duplication,
            lang=lang,
        )

        role_seq = self._resolve_role_sequence(safe_count)
        slides = result.get("slides", [])[:safe_count]
        for idx, slide in enumerate(slides):
            if idx < len(role_seq):
                slide["role_code"] = role_seq[idx]
            if avoid_title_duplication:
                fallback = str(slide.get("role") or role_seq[idx] if idx < len(role_seq) else f"Слайд {idx + 1}")
                slide["headline"] = self._strip_duplicated_title(
                    str(slide.get("headline", "")),
                    title,
                    fallback,
                )

        result["slides"] = slides
        result["slides_count"] = safe_count
        result["avoid_title_duplication"] = avoid_title_duplication

        raw_html = result.get("rich_content_html", "")
        if "ai-picchanger-rich-isolated" not in raw_html:
            result["rich_content_html"] = (
                f'<section class="ai-picchanger-rich-isolated" style="all:initial;display:block;font-family:sans-serif;">'
                f"{raw_html}</section>"
            )
        return result

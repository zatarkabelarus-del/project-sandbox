import asyncio
import base64
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
import httpx

from agents.providers.base_provider import AIProviderAdapter
from core.budget_limiter import BudgetLimiter
from core.config import get_settings, load_models_catalog
from core.exceptions import AIContentValidationError, AIProviderNetworkError
from core.security import SecretVault


class CloudAPIProvider(AIProviderAdapter):
    """Адаптер облачных ИИ-шлюзов (CLOUD_API) с контролем бюджета и AES-256 ключами."""

    provider_name: str = "cloud_api"

    OP_COSTS_USD: dict[str, float] = {
        "analyze_product": 0.015,
        "build_funnel_and_seo": 0.025,
        "generate_background": 0.040,
        "validate_slide": 0.010,
    }

    def __init__(
        self,
        api_key: str | None = None,
        encrypted_api_key: str | None = None,
        gateway_url: str | None = None,
        vision_model: str = "gpt-4o-mini",
        text_model: str = "gpt-4o-mini",
        image_model: str | None = None,
        budget_limiter: BudgetLimiter | None = None,
        timeout: float = 45.0,
    ) -> None:
        settings = get_settings()
        catalog_default = load_models_catalog().get("default_model", "gemini-nano-banana-2.1")
        raw_url = (gateway_url or os.getenv("CLOUD_API_URL", "https://aiai.by")).strip().rstrip("/")
        if raw_url in ("https://aiai.by", "http://aiai.by", "https://api.aiai.by", "http://aiai.by"):
            raw_url = "https://aiai.by"
        elif raw_url.endswith("api.aiai.by"):
            raw_url = f"{raw_url}/v1"
        self.gateway_url = raw_url
        self.vision_model = os.getenv("CLOUD_VISION_MODEL", vision_model)
        self.text_model = os.getenv("CLOUD_TEXT_MODEL", text_model)
        self.image_model = image_model or os.getenv("CLOUD_IMAGE_MODEL", catalog_default)
        self.budget = budget_limiter or BudgetLimiter(daily_limit_usd=settings.daily_budget_limit_usd)
        self.timeout = timeout

        if encrypted_api_key:
            vault = SecretVault(settings.master_key)
            self._api_key = vault.decrypt_secret(encrypted_api_key)
        else:
            self._api_key = api_key or os.getenv("CLOUD_API_KEY", "")

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AIProviderNetworkError("CLOUD_API key is missing in SecretVault or environment")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post_with_retry(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.gateway_url}/{endpoint.lstrip('/')}"
        delays = [2, 4, 8]
        last_exc: Exception | None = None

        for attempt in range(len(delays) + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                body_preview = exc.response.text[:300] if exc.response is not None else ""
                if exc.response is not None and exc.response.status_code in (400, 401, 403, 404):
                    raise AIProviderNetworkError(
                        f"Cloud API HTTP {exc.response.status_code} ({url}): {body_preview}"
                    ) from exc
                last_exc = exc
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])

        raise AIProviderNetworkError(f"Cloud API request failed after retries: {last_exc}") from last_exc

    @staticmethod
    def _extract_json_content(raw_response: dict[str, Any]) -> dict[str, Any]:
        try:
            first_choice = next(iter(raw_response["choices"]))
            content = str(first_choice["message"]["content"]).strip()
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content)
            return json.loads(content)
        except (KeyError, StopIteration, TypeError, json.JSONDecodeError) as exc:
            raise AIContentValidationError(f"Invalid JSON structure from Cloud API: {exc}") from exc

    @staticmethod
    def _normalize_image_input(image_url: Any) -> str:
        if isinstance(image_url, list):
            image_url = next(iter(image_url), "")
        url_str = str(image_url or "").strip()
        if not url_str or url_str.startswith(("http://", "https://", "data:image/")):
            return url_str
        clean_path = url_str.lstrip("/")
        project_root = Path(__file__).resolve().parents[3]
        candidates = [Path(url_str), Path.cwd() / clean_path, project_root / clean_path]
        for path_obj in candidates:
            if path_obj.is_file():
                mime_type, _ = mimetypes.guess_type(str(path_obj))
                b64_data = base64.b64encode(path_obj.read_bytes()).decode("ascii")
                return f"data:{mime_type or 'image/webp'};base64,{b64_data}"
        return url_str

    async def analyze_product(
        self,
        product_id: str,
        title: str,
        image_url: str,
        enable_vision: bool = True,
        lang: str = "ru",
    ) -> dict[str, Any]:
        if not enable_vision:
            return {
                "product_id": product_id,
                "vision_enabled": False,
                "detected_bbox": [0.2, 0.22, 0.8, 0.78],
                "dominant_colors": ["#F5F5F5", "#222222"],
                "key_features": [title],
            }

        self.budget.check_and_consume("analyze_product", self.OP_COSTS_USD["analyze_product"])
        payload = {
            "model": self.vision_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Return JSON with keys: detected_bbox (list of 4 floats 0..1), dominant_colors (list of hex), key_features (list of strings).",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Analyze product '{title}' (ID: {product_id}), lang={lang}."},
                        {"type": "image_url", "image_url": {"url": self._normalize_image_input(image_url)}},
                    ],
                },
            ],
        }
        raw = await self._post_with_retry("/chat/completions", payload)
        parsed = self._extract_json_content(raw)
        return {
            "product_id": product_id,
            "vision_enabled": True,
            "detected_bbox": parsed.get("detected_bbox", [0.2, 0.22, 0.8, 0.78]),
            "dominant_colors": parsed.get("dominant_colors", ["#F5F5F5", "#1F2937"]),
            "key_features": parsed.get("key_features", [title]),
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
        self.budget.check_and_consume("build_funnel_and_seo", self.OP_COSTS_USD["build_funnel_and_seo"])
        safe_count = max(1, min(8, int(slides_count)))
        dup_rule = (
            " Do NOT repeat or duplicate the full product title on slide headlines or badges; put only benefits and specs."
            if avoid_title_duplication
            else ""
        )
        payload = {
            "model": self.text_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Return JSON with keys: slides (exact list of {safe_count} objects with slide_index, role, headline, subheadline, badge), "
                        f"rich_content_html (isolated div without global styles), seo (meta_title, meta_description, slug).{dup_rule}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "product_id": product_id,
                            "title": title,
                            "attributes": attributes,
                            "slides_count": safe_count,
                            "avoid_title_duplication": avoid_title_duplication,
                            "lang": lang,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        raw = await self._post_with_retry("/chat/completions", payload)
        parsed = self._extract_json_content(raw)
        return {
            "product_id": product_id,
            "slides": parsed.get("slides", []),
            "avoid_title_duplication": avoid_title_duplication,
            "rich_content_html": parsed.get("rich_content_html", f"<div class='ai-rich-block'><h2>{title}</h2></div>"),
            "seo": parsed.get("seo", {"meta_title": title, "meta_description": title, "slug": product_id.lower()}),
        }

    async def generate_background(
        self,
        product_id: str,
        style_archetype: str,
        mode: str = "studio",
        bbox: list[float] | None = None,
        image_model: str | None = None,
    ) -> dict[str, Any]:
        self.budget.check_and_consume("generate_background", self.OP_COSTS_USD["generate_background"])
        safe_bbox = bbox or [0.2, 0.22, 0.8, 0.78]
        active_model = image_model or self.image_model
        payload = {
            "model": active_model,
            "prompt": (
                f"Empty {mode} product photography backdrop, style {style_archetype}. "
                f"CRITICAL: NO product, NO object, NO device, NO tools in the center; keep an empty clean surface/pedestal "
                f"in area {safe_bbox} for later product placement, soft studio lighting, blurred background depth, strictly NO text, NO letters, NO watermarks."
            ),
            "size": "1024x1024",
            "response_format": "b64_json",
        }
        raw = await self._post_with_retry("/images/generations", payload)
        data_list = raw.get("data") or [{}]
        first_item = data_list[0] if isinstance(data_list, list) and data_list else {}
        bg_b64 = str(first_item.get("b64_json", "") or "")
        bg_url = str(first_item.get("url", "") or "")
        if not bg_b64 and bg_url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                img_resp = await client.get(bg_url)
                if img_resp.status_code == 200:
                    bg_b64 = base64.b64encode(img_resp.content).decode("ascii")
        return {
            "product_id": product_id,
            "style_archetype": style_archetype,
            "mode": mode,
            "image_model": active_model,
            "safe_bbox": safe_bbox,
            "background_base64": bg_b64,
            "background_url": bg_url,
        }

    async def validate_slide(
        self,
        product_id: str,
        slide_index: int,
        layout_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.budget.check_and_consume("validate_slide", self.OP_COSTS_USD["validate_slide"])
        payload = {
            "model": self.vision_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Audit slide layout JSON. Return JSON with keys: passed (bool), score (float 0..1), issues (list of strings).",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"product_id": product_id, "slide_index": slide_index, "layout_schema": layout_schema},
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        raw = await self._post_with_retry("/chat/completions", payload)
        parsed = self._extract_json_content(raw)
        return {
            "product_id": product_id,
            "slide_index": slide_index,
            "passed": bool(parsed.get("passed", True)),
            "score": float(parsed.get("score", 0.95)),
            "issues": parsed.get("issues", []),
        }

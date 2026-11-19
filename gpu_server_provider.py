import asyncio
import os
import time
from typing import Any
import httpx

from agents.providers.base_provider import AIProviderAdapter
from core.exceptions import AIProviderNetworkError


class GPUServerProvider(AIProviderAdapter):
    """Коннектор к выделенному GPU-серверу (Flux, Qwen-VL, RMBG-2.0) с автостопом при простое."""

    provider_name: str = "gpu_server"

    def __init__(
        self,
        server_url: str | None = None,
        api_token: str | None = None,
        autostop_webhook_url: str | None = None,
        idle_timeout_sec: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.server_url = (server_url or os.getenv("GPU_SERVER_URL", "http://localhost:8080")).rstrip("/")
        self.api_token = api_token or os.getenv("GPU_SERVER_TOKEN", "")
        self.autostop_webhook_url = autostop_webhook_url or os.getenv("GPU_AUTOSTOP_WEBHOOK_URL", "")
        self.idle_timeout_sec = idle_timeout_sec or int(os.getenv("GPU_IDLE_TIMEOUT_SEC", "900"))
        self.timeout = timeout

        self.last_activity_ts: float = time.monotonic()
        self.is_stopped: bool = False
        self._watchdog_task: asyncio.Task[None] | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _touch_activity(self) -> None:
        self.last_activity_ts = time.monotonic()
        self.is_stopped = False
        if self.autostop_webhook_url and (self._watchdog_task is None or self._watchdog_task.done()):
            try:
                loop = asyncio.get_running_loop()
                self._watchdog_task = loop.create_task(self._idle_watchdog())
            except RuntimeError:
                pass

    async def _idle_watchdog(self) -> None:
        while not self.is_stopped:
            await asyncio.sleep(min(30, max(1, self.idle_timeout_sec // 2)))
            idle_elapsed = time.monotonic() - self.last_activity_ts
            if idle_elapsed >= self.idle_timeout_sec:
                await self.trigger_autostop()
                break

    async def trigger_autostop(self) -> bool:
        """Принудительная или автоматическая остановка GPU-инстанса при простое."""
        if self.is_stopped or not self.autostop_webhook_url:
            self.is_stopped = True
            return True
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.autostop_webhook_url, headers=self._headers())
                resp.raise_for_status()
            self.is_stopped = True
            return True
        except httpx.HTTPError:
            return False

    async def _post_inference(self, route: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._touch_activity()
        url = f"{self.server_url}/{route.lstrip('/')}"
        delays = [2, 4, 8]
        last_exc: Exception | None = None

        for attempt in range(len(delays) + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)
                    resp.raise_for_status()
                    self._touch_activity()
                    return resp.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])

        raise AIProviderNetworkError(f"GPU Server inference failed on {route}: {last_exc}") from last_exc

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
        return await self._post_inference(
            "/v1/qwen-vl/analyze",
            {"product_id": product_id, "title": title, "image_url": image_url, "lang": lang},
        )

    async def build_funnel_and_seo(
        self,
        product_id: str,
        title: str,
        attributes: dict[str, Any],
        slides_count: int = 5,
        lang: str = "ru",
    ) -> dict[str, Any]:
        return await self._post_inference(
            "/v1/llm/funnel-seo",
            {
                "product_id": product_id,
                "title": title,
                "attributes": attributes,
                "slides_count": slides_count,
                "lang": lang,
            },
        )

    async def generate_background(
        self,
        product_id: str,
        style_archetype: str,
        mode: str = "studio",
        bbox: list[float] | None = None,
    ) -> dict[str, Any]:
        return await self._post_inference(
            "/v1/flux/generate-bg",
            {
                "product_id": product_id,
                "style_archetype": style_archetype,
                "mode": mode,
                "bbox": bbox or [0.2, 0.22, 0.8, 0.78],
            },
        )

    async def validate_slide(
        self,
        product_id: str,
        slide_index: int,
        layout_schema: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._post_inference(
            "/v1/qwen-vl/validate",
            {"product_id": product_id, "slide_index": slide_index, "layout_schema": layout_schema},
        )

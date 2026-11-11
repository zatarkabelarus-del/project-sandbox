from typing import Any
import httpx
from connectors.base_connector import BaseCMSConnector
from core.exceptions import CMSConnectorError


class WooCommerceConnector(BaseCMSConnector):
    """Коннектор WordPress / WooCommerce REST API + AI Catalog Bridge."""

    platform_name = "woocommerce"

    def __init__(self, base_url: str, consumer_key: str, consumer_secret: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = (consumer_key, consumer_secret)
        self.timeout = timeout

    def _normalize_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        attrs = {
            item.get("name", ""): ", ".join(item.get("options", []))
            for item in raw.get("attributes", [])
            if item.get("name")
        }
        categories = [c.get("name", "") for c in raw.get("categories", []) if c.get("name")]
        images = [img.get("src", "") for img in raw.get("images", []) if img.get("src")]

        return {
            "external_id": str(raw.get("id", "")),
            "sku": raw.get("sku") or f"wc-{raw.get('id', '0')}",
            "title": raw.get("name", ""),
            "category_name": categories[0] if categories else "",
            "price": float(raw["price"]) if raw.get("price") else None,
            "attributes": attrs,
            "raw_description": raw.get("description", ""),
            "source_images": images,
        }

    async def check_connection(self) -> bool:
        url = f"{self.base_url}/wp-json/wc/v3/system_status"
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"WooCommerce connection failed: {exc}") from exc

    async def fetch_categories(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/wp-json/wc/v3/products/categories"
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url, params={"per_page": 100})
                resp.raise_for_status()
                return [
                    {"external_id": str(c["id"]), "name": c.get("name", ""), "slug": c.get("slug", ""), "count": c.get("count", 0)}
                    for c in resp.json()
                ]
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to fetch WooCommerce categories: {exc}") from exc

    async def fetch_products(self, page: int = 1, per_page: int = 50) -> list[dict[str, Any]]:
        url = f"{self.base_url}/wp-json/wc/v3/products"
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url, params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                return [self._normalize_product(item) for item in resp.json()]
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to fetch WooCommerce products: {exc}") from exc

    async def upload_media_with_seo(self, file_bytes: bytes, filename_slug: str, alt_text: str, title_text: str) -> dict[str, Any]:
        bridge_url = f"{self.base_url}/wp-json/ai-catalog-bridge/v1/media"
        files = {"file": (filename_slug, file_bytes, "image/webp")}
        data = {"alt_text": alt_text, "title": title_text}
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.post(bridge_url, files=files, data=data)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to upload media via WP Bridge: {exc}") from exc

    async def push_product_package(
        self, external_product_id: str, media_ids: list[int | str], isolated_rich_html: str, seo_meta: dict[str, Any]
    ) -> dict[str, Any]:
        url = f"{self.base_url}/wp-json/wc/v3/products/{external_product_id}"
        payload: dict[str, Any] = {
            "description": isolated_rich_html,
            "images": [{"id": int(mid)} for mid in media_ids if str(mid).isdigit()],
            "meta_data": [
                {"key": "_yoast_wpseo_title", "value": seo_meta.get("meta_title", "")},
                {"key": "_yoast_wpseo_metadesc", "value": seo_meta.get("meta_description", "")},
                {"key": "rank_math_title", "value": seo_meta.get("meta_title", "")},
                {"key": "rank_math_description", "value": seo_meta.get("meta_description", "")},
            ],
        }
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.put(url, json=payload)
                resp.raise_for_status()
                return {"updated": True, "external_product_id": external_product_id}
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to update WooCommerce product {external_product_id}: {exc}") from exc

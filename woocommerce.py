from typing import Any
import httpx
from connectors.base_connector import BaseCMSConnector
from connectors.content_protector import extract_embedded_blocks
from core.exceptions import CMSConnectorError


class WooCommerceConnector(BaseCMSConnector):
    """Коннектор WordPress / WooCommerce REST API + AI Catalog Bridge."""

    platform_name = "woocommerce"

    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        bridge_token: str | None = None,
        wp_username: str | None = None,
        wp_app_password: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = (consumer_key, consumer_secret)
        self.wp_auth = (wp_username, wp_app_password) if (wp_username and wp_app_password) else self.auth
        self.bridge_token = bridge_token
        self.timeout = timeout

    def _build_bridge_headers(self) -> dict[str, str]:
        return {"X-Bridge-Auth": self.bridge_token} if self.bridge_token else {}

    def _normalize_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        attrs = {
            item.get("name", ""): ", ".join(item.get("options", []))
            for item in raw.get("attributes", [])
            if item.get("name")
        }
        categories = [c.get("name", "") for c in raw.get("categories", []) if c.get("name")]
        images = [img.get("src", "") for img in raw.get("images", []) if img.get("src")]
        raw_short = raw.get("short_description", "") or ""
        raw_desc = raw.get("description", "") or ""

        return {
            "external_id": str(raw.get("id", "")),
            "sku": raw.get("sku") or f"wc-{raw.get('id', '0')}",
            "title": raw.get("name", ""),
            "category_name": categories[0] if categories else "",
            "price": float(raw["price"]) if raw.get("price") else None,
            "attributes": attrs,
            "raw_short_description": raw_short,
            "raw_description": raw_desc,
            "embedded_blocks": extract_embedded_blocks(raw_short, raw_desc),
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
                    {
                        "external_id": str(c["id"]),
                        "name": c.get("name", ""),
                        "slug": c.get("slug", ""),
                        "count": c.get("count", 0),
                        "description": c.get("description", ""),
                    }
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

    async def upload_media_with_seo(
        self, file_bytes: bytes, filename_slug: str, alt_text: str, title_text: str
    ) -> dict[str, Any]:
        bridge_url = f"{self.base_url}/wp-json/ai-catalog-bridge/v1/media"
        clean_filename = filename_slug if filename_slug.endswith(".webp") else f"{filename_slug}.webp"
        files = {"file": (clean_filename, file_bytes, "image/webp")}
        data = {"alt_text": alt_text, "title": title_text, "slug": clean_filename.rsplit(".", 1)[0]}
        try:
            async with httpx.AsyncClient(
                auth=self.wp_auth, headers=self._build_bridge_headers(), timeout=self.timeout
            ) as client:
                resp = await client.post(bridge_url, files=files, data=data)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to upload media via WP Bridge: {exc}") from exc

    async def push_product_package(
        self,
        external_product_id: str,
        media_ids: list[int | str],
        isolated_rich_html: str,
        seo_meta: dict[str, Any],
        short_description_html: str | None = None,
        dry_run: bool = False,
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
        if short_description_html is not None:
            payload["short_description"] = short_description_html
        if dry_run:
            return {
                "updated": False,
                "preview_only": True,
                "target_url": url,
                "external_product_id": external_product_id,
                "payload": payload,
            }
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.put(url, json=payload)
                resp.raise_for_status()
                return {"updated": True, "preview_only": False, "external_product_id": external_product_id}
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to update WooCommerce product {external_product_id}: {exc}") from exc

    async def push_category_seo(
        self, external_category_id: str, seo_text: str, meta_title: str, meta_description: str, dry_run: bool = False
    ) -> dict[str, Any]:
        url = f"{self.base_url}/wp-json/wc/v3/products/categories/{external_category_id}"
        payload = {
            "description": seo_text,
            "meta_data": [
                {"key": "_yoast_wpseo_title", "value": meta_title},
                {"key": "_yoast_wpseo_metadesc", "value": meta_description},
                {"key": "rank_math_title", "value": meta_title},
                {"key": "rank_math_description", "value": meta_description},
            ],
        }
        if dry_run:
            return {"updated": False, "preview_only": True, "external_category_id": external_category_id, "payload": payload}
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.put(url, json=payload)
                resp.raise_for_status()
                return {"updated": True, "preview_only": False, "external_category_id": external_category_id}
        except httpx.HTTPError as exc:
            raise CMSConnectorError(f"Failed to update category {external_category_id}: {exc}") from exc

import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from connectors.content_protector import extract_embedded_blocks
from connectors.woocommerce import WooCommerceConnector
from core.security import SecretVault
from database.models import Product, Store

DEFAULT_STORE_SETTINGS: dict[str, Any] = {
    "short_description_suffix": "",
    "keep_existing_shortcodes": True,
    "description_before_shortcode": True,
    "keep_existing_video": True,
    "description_before_video": False,
}


def decrypt_store_credentials(store: Store, vault: SecretVault) -> dict[str, str]:
    """Расшифровывает единый JSON-пакет секретов магазина."""
    if not store.encrypted_credentials:
        return {}
    raw_json = vault.decrypt_secret(store.encrypted_credentials)
    data = json.loads(raw_json)
    return {str(k): str(v) for k, v in data.items() if v}


def encrypt_store_credentials(
    vault: SecretVault,
    new_creds: dict[str, str | None],
    existing_store: Store | None = None,
) -> str:
    """Мержит новые ключи с существующими и шифрует единым AES-256 пакетом."""
    merged: dict[str, str] = {}
    if existing_store and existing_store.encrypted_credentials:
        merged.update(decrypt_store_credentials(existing_store, vault))
    for key, val in new_creds.items():
        if val is not None and val.strip():
            merged[key] = val.strip()
    return vault.encrypt_secret(json.dumps(merged, ensure_ascii=False)) if merged else ""


def serialize_store_public(store: Store, vault: SecretVault) -> dict[str, Any]:
    """Формирует безопасный DTO магазина для фронтенда (Zero-Frontend Secrets)."""
    creds = decrypt_store_credentials(store, vault)
    masked = {k: vault.mask_secret(v) for k, v in creds.items() if v}
    settings = {**DEFAULT_STORE_SETTINGS, **(store.settings_json or {})}
    return {
        "id": store.id,
        "name": store.name,
        "platform": store.platform,
        "base_url": store.base_url,
        "is_active": store.is_active,
        "masked_credentials": masked,
        "settings": settings,
    }


def build_woocommerce_connector(
    store: Store | None,
    vault: SecretVault,
    override_url: str | None = None,
    override_key: str | None = None,
    override_secret: str | None = None,
    override_bridge: str | None = None,
) -> WooCommerceConnector:
    """Собирает WooCommerceConnector из записи Store с возможностью переопределения параметров."""
    creds = decrypt_store_credentials(store, vault) if store else {}
    return WooCommerceConnector(
        base_url=(override_url or (store.base_url if store else "")).strip(),
        consumer_key=(override_key or creds.get("consumer_key", "")).strip(),
        consumer_secret=(override_secret or creds.get("consumer_secret", "")).strip(),
        bridge_token=(override_bridge or creds.get("bridge_token") or None),
        wp_username=creds.get("wp_username") or None,
        wp_app_password=creds.get("wp_app_password") or None,
    )


async def upsert_synced_products(
    db: AsyncSession,
    store_id: int,
    normalized_items: list[dict[str, Any]],
) -> list[int]:
    """Сохраняет или обновляет товары из CMS в локальной БД с сохранением embedded_blocks."""
    synced_ids: list[int] = []
    for item in normalized_items:
        ext_id = str(item.get("external_id") or "")
        stmt = select(Product).where(Product.store_id == store_id, Product.external_id == ext_id)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        raw_short = item.get("raw_short_description", "")
        raw_desc = item.get("raw_description", "")
        blocks = item.get("embedded_blocks") or extract_embedded_blocks(raw_short, raw_desc)

        if existing:
            existing.sku = item.get("sku") or existing.sku
            existing.title = item.get("title") or existing.title
            existing.category_name = item.get("category_name") or existing.category_name
            existing.price = item.get("price") if item.get("price") is not None else existing.price
            existing.attributes = item.get("attributes") or existing.attributes
            existing.raw_short_description = raw_short
            existing.raw_description = raw_desc
            existing.embedded_blocks = blocks
            existing.source_images = item.get("source_images") or existing.source_images
            await db.flush()
            synced_ids.append(existing.id)
        else:
            prod = Product(
                store_id=store_id,
                external_id=ext_id or None,
                sku=item.get("sku") or f"cms-{ext_id}",
                title=item.get("title") or "Untitled",
                category_name=item.get("category_name") or "",
                price=item.get("price"),
                attributes=item.get("attributes") or {},
                raw_short_description=raw_short,
                raw_description=raw_desc,
                embedded_blocks=blocks,
                source_images=item.get("source_images") or [],
                source_channel="cms_api",
            )
            db.add(prod)
            await db.flush()
            synced_ids.append(prod.id)
    await db.commit()
    return synced_ids

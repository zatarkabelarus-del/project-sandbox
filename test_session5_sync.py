import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["APP_MODE"] = "DEV_MOCK"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_session5.db"

from main import app  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_db():
    for f in (ROOT_DIR / "test_session5.db", BACKEND_DIR / "test_session5.db"):
        if f.exists():
            f.unlink()
    yield
    for f in (ROOT_DIR / "test_session5.db", BACKEND_DIR / "test_session5.db"):
        if f.exists():
            f.unlink()


def test_store_crud_and_aes256_masking():
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/stores",
            json={
                "name": "Test Woo Store",
                "platform": "woocommerce",
                "base_url": "https://example.org",
                "consumer_key": "ck_super_secret_key_12345",
                "consumer_secret": "cs_super_secret_val_67890",
                "bridge_token": "br_secret_token_999",
                "settings": {"short_description_suffix": "[inquiry_form id='7']"},
            },
        )
        assert create_resp.status_code == 200
        store = create_resp.json()["store"]
        store_id = store["id"]
        assert store["base_url"] == "https://example.org"
        assert "ck_super_secret_key_12345" not in str(store)
        assert store["masked_credentials"]["consumer_key"].startswith("ck_")
        assert store["settings"]["short_description_suffix"] == "[inquiry_form id='7']"

        update_resp = client.put(
            f"/api/stores/{store_id}",
            json={
                "name": "Test Woo Store Renamed",
                "platform": "woocommerce",
                "base_url": "https://example.org",
                "settings": {"short_description_suffix": "[inquiry_form id='8']"},
            },
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()["store"]
        assert updated["name"] == "Test Woo Store Renamed"
        assert "consumer_key" in updated["masked_credentials"]
        assert updated["settings"]["short_description_suffix"] == "[inquiry_form id='8']"

        check_resp = client.post(f"/api/stores/{store_id}/check-connection")
        assert check_resp.status_code == 200
        assert check_resp.json()["connected"] is True

def test_sync_catalog_and_hybrid_block_protection():
    with TestClient(app) as client:
        first_store = next(iter(client.get("/api/stores").json()["stores"]))
        store_id = first_store["id"]

        sync_resp = client.post(
            "/api/catalog/sync-woocommerce",
            json={
                "store_id": store_id,
                "mock_items": [
                    {
                        "id": 501,
                        "sku": "TECH-501",
                        "name": "Промышленный датчик давления",
                        "price": "12500",
                        "categories": [{"name": "Датчики"}],
                        "short_description": "Старое краткое описание [existing_calc id='2']",
                        "description": '<iframe src="/embed/501"></iframe><p>Старый текст</p>',
                        "images": [{"src": "/img1.jpg"}],
                    }
                ],
            },
        )
        assert sync_resp.status_code == 200
        assert sync_resp.json()["synced_count"] == 1

        pilot_resp = client.post(
            "/api/pilot/preview",
            json={"product_id": "TECH-501", "title": "Промышленный датчик давления", "slides_count": 2},
        )
        assert pilot_resp.status_code == 200
        task_id = pilot_resp.json()["task_id"]

        pub_default = client.post(
            "/api/publish/woocommerce",
            json={
                "task_id": task_id,
                "store_id": store_id,
                "short_description_override": "Новое AI краткое описание.",
                "rich_html_override": "<section>Новый AI рич-контент</section>",
                "video_url": "/media/clip.mp4",
                "keep_existing_shortcodes": True,
                "description_before_shortcode": True,
                "keep_existing_video": True,
                "description_before_video": False,
                "preview_only": True,
            },
        )
        assert pub_default.status_code == 200
        data_def = pub_default.json()
        assert data_def["protected_short_description"].startswith("Новое AI краткое описание.")
        assert "[inquiry_form id='8']" in data_def["protected_short_description"]
        assert "clip.mp4" in data_def["isolated_rich_html"]
        assert data_def["isolated_rich_html"].find("clip.mp4") < data_def["isolated_rich_html"].find("<section>")

        pub_swapped = client.post(
            "/api/publish/woocommerce",
            json={
                "task_id": task_id,
                "store_id": store_id,
                "short_description_override": "Новое AI краткое описание.",
                "rich_html_override": "<section>Новый AI рич-контент</section>",
                "video_url": "/media/clip.mp4",
                "keep_existing_shortcodes": True,
                "description_before_shortcode": False,
                "keep_existing_video": True,
                "description_before_video": True,
                "preview_only": True,
            },
        )
        data_swap = pub_swapped.json()
        assert data_swap["protected_short_description"].find("[inquiry_form id='8']") < data_swap["protected_short_description"].find("Новое AI")
        assert data_swap["isolated_rich_html"].find("<section>") < data_swap["isolated_rich_html"].find("clip.mp4")


def test_category_seo_flow():
    with TestClient(app) as client:
        first_store = next(iter(client.get("/api/stores").json()["stores"]))
        store_id = first_store["id"]
        cats = client.get(f"/api/seo/categories?store_id={store_id}").json()["categories"]
        first_cat = next(iter(cats))

        gen = client.post("/api/seo/categories/generate", json={"categories": cats}).json()["items"]
        first_gen = next(iter(gen))
        assert first_gen["meta_title"]

        pub = client.post(
            "/api/seo/categories/publish",
            json={
                "store_id": store_id,
                "external_category_id": first_gen["external_id"],
                "seo_text": first_gen["seo_text"],
                "meta_title": first_gen["meta_title"],
                "meta_description": first_gen["meta_description"],
                "preview_only": True,
            },
        )
        assert pub.status_code == 200
        assert pub.json()["preview_only"] is True

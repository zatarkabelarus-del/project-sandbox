import io
import os
import sys
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

os.environ["APP_MODE"] = "DEV_MOCK"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from graphics.image_utils import calculate_wcag_contrast, normalize_image_buffer  # noqa: E402


def test_graphics_normalization_and_wcag():
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (37, 99, 235)).save(buf, format="PNG")
    webp_bytes, meta = normalize_image_buffer(buf.getvalue())
    assert len(webp_bytes) > 0
    assert meta["normalized_size"] == [1080, 1440]
    assert calculate_wcag_contrast("#FFFFFF", "#0F172A") >= 15.0


def test_full_pilot_to_batch_pipeline():
    with TestClient(app) as client:
        # 1. Проверка библиотеки стилей
        styles_resp = client.get("/api/styles")
        assert styles_resp.status_code == 200
        assert len(styles_resp.json()["styles"]) >= 3

        # 2. Импорт прайса CSV с проверкой номера ошибочной строки
        csv_content = (
            "sku;title;category;price;power\n"
            "SKU-101;Универсальный прибор А;Техника;12500;1200W\n"
            ";Товар без артикула;Техника;5000;800W\n"
            "SKU-102;Универсальный прибор Б;Техника;14900;1500W\n"
        ).encode("utf-8")
        imp_resp = client.post(
            "/api/catalog/import-table",
            files={"file": ("price.csv", csv_content, "text/csv")},
        )
        assert imp_resp.status_code == 200
        imp_data = imp_resp.json()
        assert imp_data["valid_count"] == 2
        assert imp_data["error_count"] == 1
        assert imp_data["errors"][0]["row_number"] == 3

        # 3. Этап ПИЛОТ (генерация и остановка в PILOT_REVIEW)
        pilot_resp = client.post(
            "/api/pilot/preview",
            json={
                "product_id": "SKU-PILOT-01",
                "title": "Эталонное изделие",
                "style_archetype": "minimal_light",
                "enable_vision": True,
                "slides_count": 5,
                "lang": "ru",
            },
        )
        assert pilot_resp.status_code == 200
        pilot_data = pilot_resp.json()
        assert pilot_data["fsm_status"] == "PILOT_REVIEW"
        assert len(pilot_data["slides"]) == 5
        assert pilot_data["slides"][0]["qa_report"]["passed"] is True

        # 4. Утверждение Мастер-шаблона
        master_schema = pilot_data["slides"][0]["layout_schema"]
        approve_resp = client.post(
            "/api/pilot/approve",
            json={
                "name": "Эталонный шаблон v1",
                "pilot_product_id": pilot_data["db_product_id"],
                "style_code": "minimal_light",
                "approved_layout_schema": master_schema,
            },
        )
        assert approve_resp.status_code == 200
        tpl_id = approve_resp.json()["pilot_template_id"]

        # 5. Пакетная СЕРИЯ по утвержденному шаблону
        batch_resp = client.post(
            "/api/batch/run",
            json={
                "pilot_template_id": tpl_id,
                "product_ids": imp_data["created_product_ids"],
                "lang": "ru",
            },
        )
        assert batch_resp.status_code == 200
        summary = batch_resp.json()["batch_summary"]
        assert summary["total"] == 2
        assert summary["succeeded"] == 2
        assert summary["failed"] == 0

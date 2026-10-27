import base64
import io
import json
import os
import sys
import gc
from contextlib import asynccontextmanager
import psutil

# 1. ДИНАМИЧЕСКАЯ ПОДСТРАХОВКА ПУТЕЙ
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

# Сторонние библиотеки
from fastapi import FastAPI, HTTPException, UploadFile, Form, Response, Depends
from PIL import Image
import uvicorn

# Абсолютные импорты нашего проекта
from server_backend.image_processing.pipeline import ImageProcessingPipeline
from server_backend.exceptions import AppBaseException, TokenValidationError

# Глобальные параметры масштабируемости
SYS_MODE = "HYBRID"
CONCURRENCY_LIMIT = 1
pipeline = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, SYS_MODE, CONCURRENCY_LIMIT
    
    # Автоопределение характеристик под регламент ПК 1 / ПК 2 / ПК 3
    total_ram = psutil.virtual_memory().total / (1024 ** 3)
    cpu_cores = os.cpu_count() or 1
    
    if total_ram <= 4.5:
        SYS_MODE = "PK1_TEST"
        CONCURRENCY_LIMIT = 1
    elif total_ram <= 9.0:
        SYS_MODE = "HYBRID"
        CONCURRENCY_LIMIT = max(1, cpu_cores // 2)
    else:
        SYS_MODE = "PRODUCTION"
        CONCURRENCY_LIMIT = cpu_cores

    print(f"\n[🚀 ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ NEW_PROJECT_PHOTO]")
    print(f"Доступная RAM: {total_ram:.2f} GB | Ядер CPU: {cpu_cores}")
    print(f"Режим архитектуры: {SYS_MODE} | Лимит одновременных потоков: {CONCURRENCY_LIMIT}\n")
    
    pipeline = ImageProcessingPipeline(mode=SYS_MODE, api_key=os.getenv("EXTERNAL_AI_KEY"))
    yield
    pipeline = None
    gc.collect()

app = FastAPI(title="NEW_PROJECT_PHOTO Backend", lifespan=lifespan)

def verify_user_tokens(required_tokens: int = 1):
    """Проверка баланса токенов пользователя на уровне шлюза FastAPI"""
    user_mock_tokens = 500  # Тестовая заглушка для WooCommerce MVP
    if user_mock_tokens < required_tokens:
        raise TokenValidationError(f"Недостаточно токенов. Требуется: {required_tokens}, доступно: {user_mock_tokens}")
    return True

@app.get("/api/health")
def health_check():
    return {"status": "ok", "mode": SYS_MODE, "concurrency": CONCURRENCY_LIMIT}

@app.get("/api/products")
def get_products():
    """Возвращает тестовые 5 товаров для проверки связи"""
    return {
        "products": [
            {"id": 101, "name": "Бензопила Stihl MS 180", "price": "715.00"},
            {"id": 102, "name": "Триммер бензиновый TL52 ЛС", "price": "340.00"},
            {"id": 103, "name": "Стартер Partner 350 в сборе", "price": "23.80"},
            {"id": 104, "name": "Триммерная головка M10", "price": "16.80"},
            {"id": 105, "name": "Свеча зажигания Winzor 2Т", "price": "5.00"}
        ]
    }

@app.post("/api/v1/process-image")
async def process_image(
    file: UploadFile,
    shadow: str = Form("true"),
    scale: str = Form("0.85"),
    watermark_pos: str = Form("bottom_right"),
    has_tokens: bool = Depends(verify_user_tokens)
):
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Файл пуст")

        shadow_bool = shadow.lower() in ["true", "1", "yes"]
        try:
            scale_float = float(scale)
        except (ValueError, TypeError):
            scale_float = 0.85

        # Запуск обработки в адаптивном In-Memory конвейере
        processed_bytes = pipeline.process_stream(
            image_bytes=image_bytes, 
            shadow=shadow_bool, 
            scale=scale_float, 
            watermark_pos=watermark_pos
        )

        print(f"[💰 БИЛЛИНГ]: Успешно списан 1 токен за обработку фото.")
        return Response(content=processed_bytes, media_type="image/jpeg")

    except AppBaseException as custom_err:
        raise HTTPException(status_code=custom_err.code, detail=custom_err.message)
    except Exception as e:
        import traceback
        print("[🔴 КРИТИЧЕСКИЙ СБОЙ В КОНВЕЙЕРЕ БЭКЕНДА]:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка конвейера: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("server_backend.main:app", host="127.0.0.1", port=8000, reload=True)

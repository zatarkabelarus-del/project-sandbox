import base64
import io
import json
import os
import sys
from contextlib import asynccontextmanager

# 1. ДИНАМИЧЕСКАЯ ПОДСТРАХОВКА ПУТЕЙ
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

# Сторонние библиотеки (добавляем UploadFile, Form, Response)
from fastapi import FastAPI, HTTPException, UploadFile, Form, Response
from PIL import Image
import uvicorn

# Абсолютные импорты нашего проекта
from server_backend.image_processing.pipeline import ImageProcessingPipeline

pipeline = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    pipeline = ImageProcessingPipeline()
    yield
    pass

app = FastAPI(title="NEW_PROJECT_PHOTO Backend", lifespan=lifespan)

# --- Далее идут ваши @app.post / @app.get методы ---
# (Оставьте ваш код эндпоинтов без изменений здесь)


# 4. АВТОЗАПУСК СЕРВЕРА (добавьте в самый конец файла main.py)
if __name__ == "__main__":
    uvicorn.run("server_backend.main:app", host="127.0.0.1", port=8000, reload=True)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


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
    file: UploadFile,  # FastAPI автоматически перехватит файл от requests.post
    shadow: str = Form("true"),
    scale: str = Form("0.85"),
    watermark_pos: str = Form("bottom_right")
):
    try:
        # 1. Считываем чистые бинарные байты файла напрямую из сетевого потока в память
        image_bytes = await file.read()
        
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Файл пуст")

        # 2. Бережно приводим строковые параметры формы к нужным типам
        shadow_bool = shadow.lower() in ["true", "1", "yes"]
        
        try:
            scale_float = float(scale)
        except (ValueError, TypeError):
            scale_float = 0.85

        # 3. Запускаем обработку в ОЗУ-конвейере
        # ImageValidator приведет пропорции пульта к стандарту маркетплейса 1:1 (квадрат)
        processed_bytes = pipeline.process_stream(
            image_bytes=image_bytes, 
            shadow=shadow_bool, 
            scale=scale_float, 
            watermark_pos=watermark_pos
        )

        # 4. ВОЗВРАЩАЕМ СЫРЫЕ БАЙТЫ (как и ждет requests.content на клиенте)
        # Это исключает любые ошибки кодирования UTF-8/Base64
        return Response(content=processed_bytes, media_type="image/jpeg")

    except Exception as e:
        import traceback
        print("[🔴 КРИТИЧЕСКИЙ СБОЙ В КОНВЕЙЕРЕ БЭКЕНДА]:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка конвейера: {str(e)}")

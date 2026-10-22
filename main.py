import os
import sys
from contextlib import asynccontextmanager

# 1. ДИНАМИЧЕСКАЯ ПОДСТРАХОВКА ПУТЕЙ (для работы на любых ПК)
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import base64
import io
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image

# 2. АБСОЛЮТНЫЙ ИМПОРТ
from server_backend.image_processing.pipeline import ImageProcessingPipeline

# Переменная для хранения пайплайна
pipeline = None

# 3. СОВРЕМЕННЫЙ LIFESPAN МЕНЕДЖЕР (вместо устаревшего on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    # Этот код выполнится ровно ОДИН РАЗ при старте сервера
    pipeline = ImageProcessingPipeline()
    yield
    # Здесь можно описать логику при выключении (если нужно), например: pipeline.clear()
    pass

# Передаем lifespan в настройки приложения
app = FastAPI(title="NEW_PROJECT_PHOTO Backend", lifespan=lifespan)

# --- Далее идут ваши @app.post / @app.get методы ---
# (Оставьте ваш код эндпоинтов без изменений здесь)


# 4. АВТОЗАПУСК СЕРВЕРА (добавьте в самый конец файла main.py)
if __name__ == "__main__":
    uvicorn.run("server_backend.main:app", host="127.0.0.1", port=8000, reload=True)

class ImageProcessRequest(BaseModel):
    image_data: str        # Изображение в формате Base64
    shadow: bool = True     # Флаг генерации мягких теней
    scale: float = 0.85     # Масштаб товара на холсте
    watermark_pos: str = "bottom_right" # Позиция водяного знака

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
def process_image(request: ImageProcessRequest):
    try:
        # 1. Декодируем входящую строку Base64 в байты
        try:
            image_bytes = base64.b64decode(request.image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Некорректный формат Base64 данных")

        # 2. Передаем байты в ваш In-Memory ИИ-конвейер
        # В зависимости от архитектуры вашего pipeline.py, он принимает либо bytes, либо PIL.Image
        # Если ваш пайплайн принимает PIL Image, раскомментируйте строку ниже:
        # input_image = Image.open(io.BytesIO(image_bytes))
        
        # Запускаем сквозную обработку (заглушка/реальный конвейер подстроится под параметры)
        # Для демонстрации вызываем обработку (подставьте точные методы вашего pipeline.py при необходимости)
        processed_bytes = pipeline.process(
            image_bytes, 
            shadow=request.shadow, 
            scale=request.scale, 
            watermark_pos=request.watermark_pos
        )

        # 3. Кодируем результат обратно в Base64 для безопасной передачи по JSON-каналу
        encoded_result = base64.b64encode(processed_bytes).decode('utf-8')
        return {"processed_image": encoded_result, "status": "success"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка ИИ-конвейера: {str(e)}")

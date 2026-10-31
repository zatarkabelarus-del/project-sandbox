# server_backend/main.py
import os
import sys
import gc
import shutil
import asyncio
from contextlib import asynccontextmanager
import psutil

# 1. ДИНАМИЧЕСКАЯ ПОДСТРАХОВКА ПУТЕЙ
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from fastapi import FastAPI, HTTPException, UploadFile, Form, Response, Depends
import uvicorn

from server_backend.image_processing.pipeline import ImageProcessingPipeline
from server_backend.exceptions import AppBaseException, TokenValidationError
from server_backend.core.queue_manager import TASK_QUEUE, TASK_STATUSES, async_worker_loop

SYS_MODE = "HYBRID"
CONCURRENCY_LIMIT = 1
pipeline = None
UPLOAD_DIR = os.path.join(base_dir, "storage", "uploads")
OUTPUT_DIR = os.path.join(base_dir, "storage", "results")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, SYS_MODE, CONCURRENCY_LIMIT
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Автоопределение характеристик системы
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
    
    # ЗАПУСК ФОНОВОГО КОНВЕЙЕРА ОЧЕРЕДЕЙ (Мгновенно, без Redis и Celery!)
    worker_task = asyncio.create_task(async_worker_loop())
    
    pipeline = ImageProcessingPipeline(mode=SYS_MODE, api_key=os.getenv("EXTERNAL_AI_KEY"))
    yield
    # Остановка ресурсов при закрытии сервера
    worker_task.cancel()
    pipeline = None
    gc.collect()

app = FastAPI(title="NEW_PROJECT_PHOTO Backend", lifespan=lifespan)

def verify_user_tokens(required_tokens: int = 1):
    user_mock_tokens = 500
    if user_mock_tokens < required_tokens:
        raise TokenValidationError(f"Недостаточно токенов. Требуется: {required_tokens}, доступно: {user_mock_tokens}")
    return True

@app.get("/api/health")
def health_check():
    return {"status": "ok", "mode": SYS_MODE, "concurrency": CONCURRENCY_LIMIT}

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
        try: scale_float = float(scale)
        except: scale_float = 0.85

        processed_bytes = pipeline.process_stream(
            image_bytes=image_bytes, shadow=shadow_bool, scale=scale_float, watermark_pos=watermark_pos
        )
        return Response(content=processed_bytes, media_type="image/jpeg")
    except AppBaseException as custom_err:
        raise HTTPException(status_code=custom_err.code, detail=custom_err.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- АСИНХРОННЫЙ ЭНДПОИНТ (ВСТРОЕННАЯ ОЧЕРЕДЬ, МАССОВАЯ ЗАГРУЗКА ДО 3000 ФОТО) ---
@app.post("/api/v1/process-async")
async def process_image_async(
    file: UploadFile,
    shadow: str = Form("true"),
    scale: str = Form("0.85"),
    watermark_pos: str = Form("bottom_right"),
    has_tokens: bool = Depends(verify_user_tokens)
):
    import uuid
    task_id = str(uuid.uuid4())
    
    file_ext = os.path.splitext(file.filename)[1] or ".jpg"
    source_path = os.path.join(UPLOAD_DIR, f"{task_id}_in{file_ext}")
    output_path = os.path.join(OUTPUT_DIR, f"{task_id}_out.png")
    
    with open(source_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    shadow_bool = shadow.lower() in ["true", "1", "yes"]
    try: scale_float = float(scale)
    except: scale_float = 0.85

    # Сохраняем задачу в локальное состояние автомата
    TASK_STATUSES[task_id] = {"status": "PENDING", "lifecycle_state": "PENDING"}

    # Кладем контекст задачи во встроенную asyncio-очередь
    await TASK_QUEUE.put({
        "task_id": task_id,
        "ctx": {
            "source_path": source_path,
            "output_path": output_path,
            "shadow": shadow_bool,
            "scale": scale_float,
            "watermark_pos": watermark_pos,
            "sys_mode": SYS_MODE,
            "api_key": os.getenv("EXTERNAL_AI_KEY")
        }
    })

    print(f"[⚡ АСИНХРОННОСТЬ]: Задача {task_id} добавлена во внутреннюю очередь бэкенда.")
    return {
        "status": "queued",
        "task_id": task_id,
        "message": "Успешно загружено, обрабатываем"
    }

@app.get("/api/v1/tasks/{task_id}")
def get_task_status(task_id: str):
    """Возвращает текущую фазу жизненного цикла задачи из RAM-хранилища"""
    status_data = TASK_STATUSES.get(task_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return status_data

if __name__ == "__main__":
    uvicorn.run("server_backend.main:app", host="127.0.0.1", port=8000, reload=True)

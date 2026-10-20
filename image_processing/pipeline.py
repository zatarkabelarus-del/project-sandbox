import io
import os
from PIL import Image

# Абсолютные импорты модулей из пакета server_backend
from server_backend.image_processing.background import BackgroundManager
from server_backend.image_processing.canvas import CanvasManager
from server_backend.image_processing.effects import EffectsManager
# Импортируем напрямую функцию наложения вотермарки
from server_backend.image_processing.overlays import apply_watermark
from server_backend.image_processing.ai_upscale import AiUpscaleManager

class ImagePipeline:
    def __init__(self):
        """Инициализация менеджеров и ИИ-моделей (загружаются один раз при старте сервера)"""
        self.background = BackgroundManager()
        self.canvas = CanvasManager()
        self.effects = EffectsManager()
        self.upscaler = AiUpscaleManager()
        
        # Задаем жесткий путь к вотермарке в корне проекта
        self.watermark_path = os.path.join(os.getcwd(), "logo.png")

    def run(self, image_bytes: bytes, add_shadow: bool = True, scale_factor: float = 0.8, wm_pos: str = "bottom-right") -> bytes:
        """
        Сквозной In-Memory ИИ-конвейер обработки.
        Принимает байты исходного фото, возвращает байты готового PNG.
        """
        # 1. Сегментация фона (rembg)
        img_no_bg = self.background.remove_background(image_bytes)
        
        # 2. Адаптация холста и масштабирование объекта
        img_canvas = self.canvas.fit_to_canvas(img_no_bg, scale=scale_factor)
        
        # 3. Добавление мягкой тени (если включено в UI)
        if add_shadow:
            img_canvas = self.effects.generate_soft_shadow(img_canvas)
            
        # 4. Повышение резкости контуров через ИИ-апскейлер (FSRCNN_x2)
        img_sharp = self.upscaler.enhance_edges(img_canvas)
        
        # Пул параметров UI ('bottom-right' -> 'bottom_right' для вашей функции)
        sanitized_wm_pos = wm_pos.replace("-", "_")

        # 5. Наложение водяного знака через вашу функцию из overlays.py
        img_final = apply_watermark(
            base_image=img_sharp,
            watermark_path=self.watermark_path,
            position=sanitized_wm_pos,
            padding=20,
            opacity=0.85
        )
        
        # 6. Экспорт финального результата в байты (In-Memory)
        output_buffer = io.BytesIO()
        img_final.save(output_buffer, format="PNG")
        return output_buffer.getvalue()

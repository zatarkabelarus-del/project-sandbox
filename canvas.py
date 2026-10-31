import os
from PIL import Image
from typing import Union

class CanvasManager:
    def __init__(self):
        self.default_dpi = 300

    def convert_to_pixels(self, value: float, unit: str, dpi: int = None) -> int:
        """Конвертирует физические величины (см, дюймы) в пиксели"""
        current_dpi = dpi if dpi else self.default_dpi
        
        if unit == "px":
            return int(value)
        elif unit == "in" or unit == "дюйм":
            return int(value * current_dpi)
        elif unit == "cm" or unit == "см":
            return int((value / 2.54) * current_dpi)
        else:
            raise ValueError(f"Неподдерживаемая единица измерения: {unit}")

    def resize_and_place_on_canvas(
        self, 
        source_image: Union[str, Image.Image],  # ИЗМЕНЕНО: теперь принимает и путь, и саму картинку
        canvas_width: float, 
        canvas_height: float, 
        unit: str = "px",
        scale_percent: float = 85.0,
        offset_x: int = 0,
        offset_y: int = 0,
        background_color: tuple = (255, 255, 255),
        dpi: int = 300
    ) -> Image.Image:
        """
        Пропорционально масштабирует объект и центрирует его на новом холсте.
        Поддерживает передачу как пути к файлу, так и объекта PIL Image напрямую из памяти.
        """
        # 1. Расчет целевых размеров холста в пикселях
        target_w = self.convert_to_pixels(canvas_width, unit, dpi)
        target_h = self.convert_to_pixels(canvas_height, unit, dpi)

        # 2. Создание чистого холста (подложки). ВАЖНО: создаем в RGBA, чтобы корректно 
        # накладывать полупрозрачные края без превращения их в артефакты
        canvas = Image.new("RGBA", (target_w, target_h), background_color + (255,))

        # 3. Получение или загрузка изображения товара
        if isinstance(source_image, str):
            if not os.path.exists(source_image):
                raise FileNotFoundError(f"Исходный файл не найден: {source_image}")
            img_context = Image.open(source_image)
        else:
            # Если передали уже открытый объект Image, работаем с его дубликатом
            img_context = source_image.copy()

        # Процесс обработки изображения
        try:
            if img_context.mode in ("RGBA", "P"):
                img = img_context.convert("RGBA")
            else:
                img = img_context.convert("RGB")

            orig_w, orig_h = img.size

            # 4. Вычисление коэффициента пропорционального сжатия
            max_allowed_w = target_w * (scale_percent / 100.0)
            max_allowed_h = target_h * (scale_percent / 100.0)

            ratio = min(max_allowed_w / orig_w, max_allowed_h / orig_h)
            
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)

            # Изменяем размер товара
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 5. Расчет координат для точного центрирования
            paste_x = (target_w - new_w) // 2 + offset_x
            paste_y = (target_h - new_h) // 2 + offset_y

            # 6. Наложение объекта на холст
            if resized_img.mode == "RGBA":
                canvas.paste(resized_img, (paste_x, paste_y), resized_img)
            else:
                canvas.paste(resized_img, (paste_x, paste_y))
                
        finally:
            # Гарантированно закрываем файл, если мы его открывали из строки
            if isinstance(source_image, str):
                img_context.close()

        return canvas

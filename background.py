import os
from PIL import Image
from rembg import remove, new_session

class BackgroundManager:
    def __init__(self):
        self.session = new_session("u2net")

    # === ЯКОРЬ НАЧАЛА: Чистое удаление фона без повреждения маски ===
    def remove_background_and_crop(self, source_image_path: str, noise_threshold: int = 15) -> Image.Image:
        """
        Удаляет фон нейросетью. Находит истинные габариты объекта 
        через виртуальную фильтрацию шума, но возвращает ОРИГИНАЛЬНЫЕ мягкие края.
        """
        if not os.path.exists(source_image_path):
            raise FileNotFoundError(f"Файл не найден: {source_image_path}")
            
        with Image.open(source_image_path) as img:
            img_rgba = img.convert("RGBA")
            no_bg_img = remove(img_rgba, session=self.session)
            
            # Разделяем каналы, чтобы проанализировать прозрачность (Альфа-канал)
            r, g, b, a = no_bg_img.split()
            
            # Виртуальная маска только для расчета BBox: отсекаем шум invisible-пикселей
            virtual_alpha = a.point(lambda p: 255 if p > noise_threshold else 0)
            cleaned_tmp = Image.merge("RGBA", (r, g, b, virtual_alpha))
            
            bbox = cleaned_tmp.getbbox()
            if bbox:
                # ВАЖНО: Обрезаем исходную ЖИВУЮ картинку (no_bg_img) по координатам виртуальной
                return no_bg_img.crop(bbox)
            
            return no_bg_img
    # === ЯКОРЬ КОНЦА: Чистое удаление фона без повреждения маски ===

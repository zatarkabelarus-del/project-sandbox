# server_backend/image_processing/background.py
import os
from PIL import Image
from server_backend.exceptions import InvalidImageError

try:
    from rembg import remove, new_session
except ImportError:
    remove, new_session = None, None

class BackgroundManager:
    def __init__(self, mode: str = "HYBRID", api_key: str = None):
        self.mode = mode.upper()
        self.api_key = api_key
        self.session = None
        
        # Инициализируем локальную ИИ-модель u2net строго в PRODUCTION контуре
        if self.mode == "PRODUCTION" and remove is not None:
            self.session = new_session("u2net")

    # === НАЧАЛО: Ваша оригинальная файловая логика с жестким контекстом with ===
    def remove_background_and_crop(self, source_image_path: str, noise_threshold: int = 15) -> Image.Image:
        """
        Удаляет фон нейросетью. Находит истинные габариты объекта 
        через виртуальную фильтрацию шума, но возвращает ОРИГИНАЛЬНЫЕ мягкие края.
        """
        if not os.path.exists(source_image_path):
            raise FileNotFoundError(f"Файл не найден: {source_image_path}")
            
        with Image.open(source_image_path) as img:
            img_rgba = img.convert("RGBA")
            
            # Разветвление стратегий в зависимости от ресурсов ПК
            if self.mode == "PK1_TEST":
                no_bg_img = img_rgba
            elif self.mode == "HYBRID":
                no_bg_img = img_rgba  # Временный MVP-Mock для внешнего API
            else:
                if remove is None or self.session is None:
                    raise InvalidImageError("Движок rembg недоступен в режиме PRODUCTION")
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
    # === КОНЕЦ: Ваша оригинальная файловая логика ===

    def process_image_object(self, img: Image.Image, noise_threshold: int = 15) -> Image.Image:
        """
        Параллельный In-Memory метод для сквозного бинарного конвейера pipeline.py.
        Принимает уже открытый в ОЗУ объект PIL, обрабатывает и возвращает PIL-объект.
        """
        try:
            img_rgba = img.convert("RGBA")
            
            if self.mode == "PK1_TEST":
                no_bg_img = img_rgba
            elif self.mode == "HYBRID":
                no_bg_img = img_rgba  # Внешнее API (посекундный / поштучный тариф)
            else:
                if remove is None or self.session is None:
                    raise InvalidImageError("Движок rembg недоступен в режиме PRODUCTION")
                no_bg_img = remove(img_rgba, session=self.session)
            
            r, g, b, a = no_bg_img.split()
            virtual_alpha = a.point(lambda p: 255 if p > noise_threshold else 0)
            cleaned_tmp = Image.merge("RGBA", (r, g, b, virtual_alpha))
            
            bbox = cleaned_tmp.getbbox()
            if bbox:
                return no_bg_img.crop(bbox)
            
            return no_bg_img

        except Exception as e:
            raise InvalidImageError(f"Ошибка ИИ-сегментации фона в ОЗУ: {str(e)}")

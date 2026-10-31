from PIL import Image

class ImageValidator:
    @staticmethod
    def enforce_aspect_ratio(image: Image.Image, target_ratio: str = "1:1", background_color: tuple = (255, 255, 255, 0)) -> Image.Image:
        """
        Умный валидатор пропорций. Приводит RAW-фото от поставщиков к стандартам e-commerce.
        Вместо грубого сжатия (растягивания) добавляет невидимые или цветные поля (paddings)
        по бокам или сверху/снизу, сохраняя физику объекта.
        """
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        width, height = image.size
        current_ratio = width / height

        # Определяем целевые пропорции
        if target_ratio == "1:1":
            req_ratio = 1.0
        elif target_ratio == "3:4":
            req_ratio = 3.0 / 4.0
        else:
            return image # Если формат не распознан, возвращаем оригинал

        # Расчет размеров нового холста
        if current_ratio > req_ratio:
            # Картинка слишком широкая — доращиваем высоту
            new_width = width
            new_height = int(width / req_ratio)
        else:
            # Картинка слишком высокая (узкая) — доращиваем ширину
            new_height = height
            new_width = int(height * req_ratio)

        # Создаем пустой холст с прозрачным или белым фоном
        valid_canvas = Image.new("RGBA", (new_width, new_height), background_color)
        
        # Вычисляем координаты центрирования
        x_offset = (new_width - width) // 2
        y_offset = (new_height - height) // 2

        # Накладываем исходный товар строго по центру холста
        valid_canvas.paste(image, (x_offset, y_offset), image)
        
        print(f"[🔍 VALIDATOR] Пропорции приведены к {target_ratio} ({width}x{height} -> {new_width}x{new_height})")
        return valid_canvas

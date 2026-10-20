import os
from PIL import Image

def apply_watermark(base_image: Image.Image, watermark_path: str, position: str = "bottom_right", padding: int = 20, opacity: float = 1.0) -> Image.Image:
    """
    Умное наложение водяного знака на изображение с сохранением прозрачности (Alpha Blending).
    
    :param base_image: Объект PIL.Image (основное изображение товара)
    :param watermark_path: Абсолютный или относительный путь к файлу вотермарки (PNG)
    :param position: Позиция ('top_left', 'top_right', 'bottom_left', 'bottom_right', 'center')
    :param padding: Отступ от краев холста в пикселях
    :param opacity: Коэффициент прозрачности вотермарки (от 0.0 до 1.0)
    :return: Новый объект PIL.Image с наложенным водяным знаком
    """
    if not os.path.exists(watermark_path):
        raise FileNotFoundError(f"Файл водяного знака не найден по пути: {watermark_path}")

    # 1. Открываем вотермарку и строго приводим к RGBA
    wm = Image.open(watermark_path).convert("RGBA")
    
    # 2. Гарантируем, что базовое изображение тоже в RGBA для попиксельного смешивания
    if base_image.mode != "RGBA":
        base_image = base_image.convert("RGBA")

    # 3. Масштабируем вотермарку, если она физически больше базового фото (защита от переполнения)
    base_w, base_h = base_image.size
    wm_w, wm_h = wm.size
    
    max_wm_width = int(base_w * 0.4)  # Вотермарка не должна занимать более 40% ширины карточки
    if wm_w > max_wm_width:
        scale_factor = max_wm_width / wm_w
        wm = wm.resize((max_wm_width, int(wm_h * scale_factor)), Image.Resampling.LANCZOS)
        wm_w, wm_h = wm.size

    # 4. Регулировка глобальной прозрачности вотермарки (если opacity < 1.0)
    if opacity < 1.0:
        r, g, b, a = wm.split()
        a = a.point(lambda p: int(p * opacity))
        wm = Image.merge("RGBA", (r, g, b, a))

    # 5. Вычисление координат наложения (X, Y)
    if position == "top_left":
        x = padding
        y = padding
    elif position == "top_right":
        x = base_w - wm_w - padding
        y = padding
    elif position == "bottom_left":
        x = padding
        y = base_h - wm_h - padding
    elif position == "center":
        x = (base_w - wm_w) // 2
        y = (base_h - wm_h) // 2
    else:  # По умолчанию: bottom_right
        x = base_w - wm_w - padding
        y = base_h - wm_h - padding

    # 6. Безопасное послойное наложение через создание временного прозрачного слоя
    overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    overlay.paste(wm, (x, y))
    
    # Смешиваем слои без разрушения краев и альфа-канала
    result_image = Image.alpha_composite(base_image, overlay)
    return result_image

import gc
import io
from typing import Any
from PIL import Image, ImageOps


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    if len(cleaned) != 6:
        return (15, 23, 42)
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for c in rgb:
        s = c / 255.0
        channels.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def calculate_wcag_contrast(fg_hex: str, bg_hex: str) -> float:
    """Расчет коэффициента контрастности текста и плашки по стандарту WCAG 2.1."""
    l1 = _relative_luminance(_hex_to_rgb(fg_hex))
    l2 = _relative_luminance(_hex_to_rgb(bg_hex))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def calculate_bbox_iou_and_overlap(
    box_a: list[float] | tuple[float, float, float, float],
    box_b: list[float] | tuple[float, float, float, float],
) -> float:
    """Доля площади box_a, перекрываемой box_b. Координаты в формате [x, y, w, h] (0.0..1.0)."""
    ax1, ay1, aw, ah = box_a
    bx1, by1, bw, bh = box_b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0

    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = max(aw * ah, 1e-6)
    return round(inter_area / area_a, 4)


def normalize_image_buffer(
    image_bytes: bytes,
    target_size: tuple[int, int] = (1080, 1440),
    output_format: str = "WEBP",
    quality: int = 90,
) -> tuple[bytes, dict[str, Any]]:
    """Потоковая нормализация изображения с обязательным освобождением памяти (del + gc.collect)."""
    img = None
    canvas = None
    out_buf = io.BytesIO()
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")

        orig_w, orig_h = img.size
        target_w, target_h = target_size

        img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (target_w, target_h), (248, 250, 252, 255))
        offset_x = (target_w - img.width) // 2
        offset_y = (target_h - img.height) // 2
        canvas.paste(img, (offset_x, offset_y), img if img.mode == "RGBA" else None)

        final_img = canvas.convert("RGB") if output_format.upper() != "PNG" else canvas
        final_img.save(out_buf, format=output_format.upper(), quality=quality)
        result_bytes = out_buf.getvalue()

        meta = {
            "original_size": [orig_w, orig_h],
            "normalized_size": [target_w, target_h],
            "product_bbox": [
                round(offset_x / target_w, 4),
                round(offset_y / target_h, 4),
                round(img.width / target_w, 4),
                round(img.height / target_h, 4),
            ],
            "format": output_format.upper(),
        }
        del final_img
        return result_bytes, meta
    finally:
        if img is not None:
            img.close()
            del img
        if canvas is not None:
            canvas.close()
            del canvas
        out_buf.close()
        gc.collect()


def generate_solid_placeholder_webp(
    color_hex: str = "#F8FAFC",
    size: tuple[int, int] = (1080, 1440),
) -> bytes:
    """Генерация легкого растрового фонового слоя с немедленной очисткой буфера."""
    rgb = _hex_to_rgb(color_hex)
    img = Image.new("RGB", size, rgb)
    buf = io.BytesIO()
    try:
        img.save(buf, format="WEBP", quality=85)
        return buf.getvalue()
    finally:
        img.close()
        del img
        buf.close()
        gc.collect()

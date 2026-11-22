import base64
import gc
import io
from typing import Any
from PIL import Image, ImageFilter, ImageOps
from core.config import AppMode, get_settings
from graphics.image_utils import _save_pil_to_buffer, resolve_output_format


def _fallback_chroma_cutout(img: Image.Image) -> Image.Image:
    """Мягкий фоллбэк без нейровесов: делает светлый/краевой студийный фон прозрачным."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    corners = [px[0, 0][:3], px[w - 1, 0][:3], px[0, h - 1][:3], px[w - 1, h - 1][:3]]
    bg_r = sum(c[0] for c in corners) // 4
    bg_g = sum(c[1] for c in corners) // 4
    bg_b = sum(c[2] for c in corners) // 4

    new_data = []
    for r, g, b, a in rgba.getdata():
        dist = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)
        if dist < 48:
            new_data.append((r, g, b, 0))
        elif dist < 78:
            alpha = int(((dist - 48) / 30.0) * a)
            new_data.append((r, g, b, alpha))
        else:
            new_data.append((r, g, b, a))
    rgba.putdata(new_data)
    alpha_band = rgba.split()[3].filter(ImageFilter.GaussianBlur(radius=0.8))
    rgba.putalpha(alpha_band)
    return rgba
def remove_background_bytes(image_bytes: bytes) -> tuple[bytes, str, str]:
    """Локальное удаление фона на CPU (rembg U2Net или студийный фоллбэк в DEV_MOCK)."""
    settings = get_settings()
    img = None
    out_img = None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGBA")
        engine_used = "studio_chroma_fallback"

        if settings.app_mode != AppMode.DEV_MOCK:
            try:
                from rembg import remove as rembg_remove  # type: ignore
                raw_png = rembg_remove(image_bytes)
                out_img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
                engine_used = "rembg_u2net"
            except Exception:
                out_img = _fallback_chroma_cutout(img)
        else:
            out_img = _fallback_chroma_cutout(img)

        png_bytes = _save_pil_to_buffer(out_img, "PNG", 95)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return png_bytes, f"data:image/png;base64,{b64}", engine_used
    finally:
        if img is not None:
            img.close()
            del img
        if out_img is not None:
            out_img.close()
            del out_img
        gc.collect()


def smart_resize_canvas(
    image_bytes: bytes,
    target_width: int = 1080,
    target_height: int = 1440,
    output_format: str = "WEBP",
    quality: int = 90,
) -> tuple[bytes, dict[str, Any]]:
    """Умный ресайз с заполнением холста без искажения пропорций (cover-crop)."""
    w = max(200, min(4096, int(target_width)))
    h = max(200, min(4096, int(target_height)))
    pil_fmt, ext, mime = resolve_output_format(output_format)
    img = None
    fitted = None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        fitted = ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        encoded = _save_pil_to_buffer(fitted, pil_fmt, quality)
        return encoded, {"width": w, "height": h, "format": pil_fmt, "extension": ext, "mime_type": mime}
    finally:
        if img is not None:
            img.close()
            del img
        if fitted is not None:
            fitted.close()
            del fitted
        gc.collect()

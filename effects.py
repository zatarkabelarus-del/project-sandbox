from PIL import Image, ImageFilter

class EffectsManager:
    # === ЯКОРЬ НАЧАЛА: Модуль независимых эффектов карточки ===
    def apply_blur_edges(self, image: Image.Image, radius: int = 0) -> Image.Image:
        """Сглаживание краев. Если радиус 0 — эффект отключен."""
        if radius <= 0:
            return image
        if image.mode != "RGBA":
            image = image.convert("RGBA")
            
        r, g, b, a = image.split()
        smoothed_a = a.filter(ImageFilter.GaussianBlur(radius))
        return Image.merge("RGBA", (r, g, b, smoothed_a))

    def create_drop_shadow(
        self, 
        image: Image.Image, 
        enabled: bool = False,
        offset_x: int = 10, 
        offset_y: int = 15, 
        blur_radius: int = 12, 
        shadow_opacity: float = 0.4
    ) -> Image.Image:
        """Генерация тени. Если enabled=False — возвращает объект без изменений."""
        if not enabled:
            return image

        if image.mode != "RGBA":
            image = image.convert("RGBA")

        r, g, b, a = image.split()
        shadow_mask = a.point(lambda p: int(p * shadow_opacity))
        
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow.putalpha(shadow_mask)
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

        pad_w = image.width + abs(offset_x) + blur_radius * 2
        pad_h = image.height + abs(offset_y) + blur_radius * 2
        
        final_layer = Image.new("RGBA", (pad_w, pad_h), (0, 0, 0, 0))
        
        shadow_x = max(0, offset_x) + blur_radius
        shadow_y = max(0, offset_y) + blur_radius
        final_layer.paste(shadow, (shadow_x, shadow_y))

        object_x = max(0, -offset_x) + blur_radius
        object_y = max(0, -offset_y) + blur_radius
        final_layer.paste(image, (object_x, object_y), image)

        return final_layer
    # === ЯКОРЬ КОНЦА: Модуль независимых эффектов карточки ===

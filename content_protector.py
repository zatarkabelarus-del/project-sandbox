import html
import re
from typing import Any

SHORTCODE_PATTERN = re.compile(r"\[[a-zA-Z0-9_-]+(?:\s+[^\]]*)?\](?:.*?\[/[a-zA-Z0-9_-]+\])?", re.DOTALL)
VIDEO_BLOCK_PATTERN = re.compile(
    r"(<video\b[^>]*>.*?</video>|<iframe\b[^>]*>.*?</iframe>|<div[^>]*class=[\"'][^\"']*video[^\"']*[\"'][^>]*>.*?</div>)",
    re.IGNORECASE | re.DOTALL,
)


def extract_embedded_blocks(raw_short_description: str = "", raw_description: str = "") -> dict[str, list[str]]:
    """Извлекает существующие шорткоды из краткого описания и видеоконтейнеры из основного."""
    shortcodes = [m.group(0).strip() for m in SHORTCODE_PATTERN.finditer(raw_short_description or "") if m.group(0).strip()]
    video_blocks = [m.group(0).strip() for m in VIDEO_BLOCK_PATTERN.finditer(raw_description or "") if m.group(0).strip()]
    return {
        "shortcodes": shortcodes,
        "video_blocks": video_blocks,
    }


def build_responsive_video_embed(video_url: str) -> str:
    """Формирует изолированный адаптивный HTML-контейнер для видео без вмешательства в тему CMS."""
    clean_url = html.escape(video_url.strip(), quote=True)
    if not clean_url:
        return ""
    if clean_url.lower().endswith((".mp4", ".webm", ".ogg")):
        return (
            '<div style="position:relative;width:100%;max-width:960px;margin:0 auto 16px auto;">'
            f'<video controls preload="metadata" style="width:100%;border-radius:12px;display:block;" src="{clean_url}"></video>'
            "</div>"
        )
    return (
        '<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin:0 auto 16px auto;">'
        f'<iframe src="{clean_url}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'
        "</div>"
    )


def compose_protected_descriptions(
    ai_short_description: str,
    ai_rich_html: str,
    embedded_blocks: dict[str, Any] | None = None,
    short_description_suffix: str = "",
    video_url: str = "",
    keep_existing_shortcodes: bool = True,
    description_before_shortcode: bool = True,
    keep_existing_video: bool = True,
    description_before_video: bool = False,
) -> dict[str, str]:
    """Собирает short_description и description по 4 правилам размещения встраиваемых блоков."""
    blocks = embedded_blocks or {}
    short_text = (ai_short_description or "").strip()
    rich_text = (ai_rich_html or "").strip()

    shortcode_parts: list[str] = []
    if keep_existing_shortcodes:
        for sc in blocks.get("shortcodes", []):
            if sc and sc not in shortcode_parts:
                shortcode_parts.append(sc)
        suffix = (short_description_suffix or "").strip()
        if suffix and suffix not in shortcode_parts:
            shortcode_parts.append(suffix)

    shortcode_chunk = "\n".join(shortcode_parts).strip()
    if shortcode_chunk and short_text:
        final_short = f"{short_text}\n{shortcode_chunk}" if description_before_shortcode else f"{shortcode_chunk}\n{short_text}"
    else:
        final_short = short_text or shortcode_chunk

    video_parts: list[str] = []
    if keep_existing_video:
        for vb in blocks.get("video_blocks", []):
            if vb and vb not in video_parts:
                video_parts.append(vb)
        if video_url and video_url.strip():
            new_embed = build_responsive_video_embed(video_url)
            if new_embed and new_embed not in video_parts:
                video_parts.append(new_embed)

    video_chunk = "\n".join(video_parts).strip()
    if video_chunk and rich_text:
        final_rich = f"{rich_text}\n{video_chunk}" if description_before_video else f"{video_chunk}\n{rich_text}"
    else:
        final_rich = rich_text or video_chunk

    return {
        "short_description": final_short,
        "description": final_rich,
    }

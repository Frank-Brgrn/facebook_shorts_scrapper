from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from pathlib import Path

from src.models import VideoRecord, build_embed_url, build_watch_url
from src.utils import extract_video_id, normalize_facebook_video_url, yaml_safe_text

CARD_MARKER = 'class="x1yztbdb"'
WATCH_LINK_RE = re.compile(
    r'href="(https://www\.facebook\.com/watch/\?ref=saved(?:&amp;|&)v=(\d+)[^"]*)"'
)
REEL_META_RE = re.compile(r">Reels\s*[•·]\s*([^<]+)<")
PROFILE_ARIA_RE = re.compile(
    r'aria-label="([^"]+)"[^>]*href="https://www\.facebook\.com/[^"]*"'
)
SPAN_TEXT_RE = re.compile(r"<span[^>]*>([^<]{1,2000})</span>")


@dataclass
class ExtractedReel:
    title: str
    author: str
    channel: str
    url: str
    video_id: str
    index: int = 0


def _decode_text(raw: str) -> str:
    return yaml_safe_text(html_lib.unescape(raw))


def _extract_title(chunk: str, watch_href: str) -> str:
    start = chunk.find(watch_href)
    if start == -1:
        return ""

    segment = chunk[start : start + 15000]
    for raw in SPAN_TEXT_RE.findall(segment):
        text = _decode_text(raw)
        if len(text) < 3:
            continue
        if re.match(r"^Reels\s*[•·]", text, re.I):
            continue
        if re.match(r"^\d{2}:\d{2}$", text):
            continue
        if text == "image":
            continue
        if re.search(r"saved from|enregistr", text, re.I):
            continue
        return text

    button = re.search(
        r'aria-label="([^"]{5,2000})"[^>]*role="button"',
        segment,
    )
    if button:
        label = _decode_text(button.group(1))
        if not re.search(r"add to collection|ajouter", label, re.I):
            return label

    return ""


def _extract_card(chunk: str, index: int) -> ExtractedReel | None:
    watch = WATCH_LINK_RE.search(chunk)
    if not watch:
        return None

    url = _decode_text(watch.group(1)).replace("&amp;", "&")
    video_id = watch.group(2)
    normalized = normalize_facebook_video_url(url) or url

    author = ""
    meta = REEL_META_RE.search(chunk)
    if meta:
        author = _decode_text(meta.group(1))

    if not author:
        profile = PROFILE_ARIA_RE.search(chunk)
        if profile:
            author = _decode_text(profile.group(1)).split(",")[0].strip()

    title = _extract_title(chunk, watch.group(1))
    if not title:
        title = f"Facebook Reel {video_id}"

    return ExtractedReel(
        title=title,
        author=author,
        channel=author,
        url=normalized,
        video_id=video_id,
        index=index,
    )


def extract_reels_from_html(html: str) -> list[ExtractedReel]:
    """Extract saved reel cards from a Saved Reels dashboard HTML dump."""
    parts = html.split(CARD_MARKER)
    if len(parts) <= 1:
        return []

    results: list[ExtractedReel] = []
    seen_ids: set[str] = set()

    for part in parts[1:]:
        next_card = part.find(CARD_MARKER)
        chunk = part[:next_card] if next_card != -1 else part

        card = _extract_card(chunk, len(results))
        if not card or card.video_id in seen_ids:
            continue

        seen_ids.add(card.video_id)
        results.append(card)

    return results


def extract_reels_from_html_file(path: Path) -> list[ExtractedReel]:
    html = path.read_text(encoding="utf-8")
    return extract_reels_from_html(html)


def extracted_reel_to_record(
    reel: ExtractedReel,
    *,
    accessed_date,
    source_label: str,
    video_type: str,
    extraction_type: str,
) -> VideoRecord:
    return VideoRecord(
        accessed_date=accessed_date,
        published_date=None,
        author=reel.author,
        channel=reel.channel or reel.author,
        title=reel.title,
        url=build_watch_url(reel.video_id),
        embed_url=build_embed_url(reel.video_id),
        source=source_label,
        type=video_type,
        video_id=reel.video_id,
        extraction_type=extraction_type,
    )

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.models import VideoRecord

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\n\r\t]')
VIDEO_ID_PATTERNS = (
    re.compile(r"[?&]v=(\d+)"),
    re.compile(r"/reel/(\d+)"),
    re.compile(r"/videos/(\d+)"),
)


def extract_video_id(url: str) -> str | None:
    for pattern in VIDEO_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "v" in query and query["v"]:
        return query["v"][0]
    return None


def normalize_facebook_video_url(url: str) -> str | None:
    video_id = extract_video_id(url)
    if not video_id:
        return None

    parsed = urlparse(url)
    if "facebook.com" not in parsed.netloc:
        return None

    return f"https://www.facebook.com/watch/?v={video_id}"


def video_dedup_keys(*urls: str, video_id: str = "") -> set[str]:
    """Return normalized identifiers used to detect duplicate Facebook videos."""
    keys: set[str] = set()
    if video_id:
        keys.add(video_id)

    for url in urls:
        if not url:
            continue
        normalized = normalize_facebook_video_url(url)
        if normalized:
            keys.add(normalized)
            extracted = extract_video_id(normalized)
            if extracted:
                keys.add(extracted)
    return keys


def find_latest_html_dump(dumps_dir: Path) -> Path | None:
    if not dumps_dir.exists():
        return None

    html_files = list(dumps_dir.glob("*.html"))
    if not html_files:
        return None

    return max(html_files, key=lambda path: path.stat().st_mtime)


def yaml_safe_text(text: str) -> str:
    """Collapse whitespace/newlines so YAML frontmatter stays on one line."""
    return " ".join(text.split())


def sanitize_filename(title: str, max_length: int = 120) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("", yaml_safe_text(title)).strip().rstrip(".")
    if not cleaned:
        cleaned = "Untitled"
    return cleaned[:max_length]


def note_filename(video: VideoRecord) -> str:
    prefix_date = video.published_date or video.accessed_date
    date_part = prefix_date.strftime("%Y%m%d")
    title_part = sanitize_filename(video.title)
    return f"{date_part} - {title_part}.md"


def parse_facebook_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if iso_match:
        return date.fromisoformat(iso_match.group(1))
    return None


def parse_publish_date(raw: str | int | float | None) -> date | None:
    if raw is None:
        return None

    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
        timestamp = int(raw)
        if timestamp > 1_000_000_000_000:
            timestamp //= 1000
        return datetime.fromtimestamp(timestamp).date()

    text = str(raw).strip()
    if not text:
        return None

    if text.isdigit():
        return parse_publish_date(int(text))

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass

    return parse_facebook_date(text)

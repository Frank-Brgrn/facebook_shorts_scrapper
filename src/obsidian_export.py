from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import Settings
from src.models import VideoRecord
from src.utils import extract_video_id, normalize_facebook_video_url, note_filename, video_dedup_keys

VIDEO_ID_LINE_RE = re.compile(r'^Video ID:\s*"?(\d+)"?\s*$', re.M)
URL_LINE_RE = re.compile(r'^URL:\s*"?([^"\n]+)"?\s*$', re.M)
EMBED_URL_LINE_RE = re.compile(r'^Embed URL:\s*"?([^"\n]+)"?\s*$', re.M)


@dataclass
class ExistingVaultVideos:
    video_ids: set[str] = field(default_factory=set)
    normalized_urls: set[str] = field(default_factory=set)

    def contains(self, video: VideoRecord) -> bool:
        keys = video_dedup_keys(video.url, video.embed_url, video_id=video.video_id)
        if keys & self.video_ids:
            return True
        return bool(keys & self.normalized_urls)

    def register(self, video: VideoRecord) -> None:
        keys = video_dedup_keys(video.url, video.embed_url, video_id=video.video_id)
        self.video_ids.update(keys)
        for url in (video.url, video.embed_url):
            normalized = normalize_facebook_video_url(url)
            if normalized:
                self.normalized_urls.add(normalized)


def _video_id_from_note(path: Path) -> str | None:
    try:
        post = frontmatter.load(path)
        video_id = post.metadata.get("Video ID")
        if video_id is not None:
            normalized = str(video_id).strip().strip('"').strip("'")
            if normalized:
                return normalized
    except Exception:
        pass

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = VIDEO_ID_LINE_RE.search(text)
    return match.group(1) if match else None


def _urls_from_note(path: Path) -> list[str]:
    urls: list[str] = []
    try:
        post = frontmatter.load(path)
        for key in ("URL", "Embed URL"):
            value = post.metadata.get(key)
            if value:
                urls.append(str(value).strip().strip('"').strip("'"))
    except Exception:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return urls
        urls.extend(URL_LINE_RE.findall(text))
        urls.extend(EMBED_URL_LINE_RE.findall(text))
    return urls


def load_existing_vault_videos(vault_dir: Path) -> ExistingVaultVideos:
    existing = ExistingVaultVideos()
    if not vault_dir.exists():
        return existing

    for path in vault_dir.glob("*.md"):
        video_id = _video_id_from_note(path)
        if video_id:
            existing.video_ids.add(video_id)

        for url in _urls_from_note(path):
            normalized = normalize_facebook_video_url(url)
            if normalized:
                existing.normalized_urls.add(normalized)
                extracted = extract_video_id(normalized)
                if extracted:
                    existing.video_ids.add(extracted)

    return existing


def load_existing_video_ids(vault_dir: Path) -> set[str]:
    return load_existing_vault_videos(vault_dir).video_ids


def filter_new_videos_for_obsidian(
    videos: list[VideoRecord], existing: ExistingVaultVideos
) -> tuple[list[VideoRecord], int]:
    new_videos: list[VideoRecord] = []
    skipped = 0

    for video in videos:
        if existing.contains(video):
            skipped += 1
            continue
        new_videos.append(video)
        existing.register(video)

    return new_videos, skipped


def _ensure_unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def export_obsidian_notes(
    videos: list[VideoRecord], settings: Settings
) -> tuple[list[Path], int]:
    settings.obsidian_vault_dir.mkdir(parents=True, exist_ok=True)
    existing = load_existing_vault_videos(settings.obsidian_vault_dir)
    new_videos, skipped = filter_new_videos_for_obsidian(videos, existing)

    env = Environment(
        loader=FileSystemLoader(settings.template_path.parent),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(settings.template_path.name)

    created_paths: list[Path] = []
    for video in new_videos:
        content = template.render(v=video.to_template_context())
        output_path = _ensure_unique_path(
            settings.obsidian_vault_dir,
            note_filename(video),
        )
        output_path.write_text(content, encoding="utf-8")
        created_paths.append(output_path)

    return created_paths, skipped

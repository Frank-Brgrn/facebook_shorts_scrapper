from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import frontmatter

from src.config import Settings, get_settings
from src.models import VideoRecord
from src.obsidian_export import _video_id_from_note
from src.obsidian_repair import (
    FRONTMATTER_KEYS,
    _clean_field_value,
    _normalize_body,
    _parse_frontmatter_block,
    _render_frontmatter,
    _split_frontmatter,
    repair_note_content,
)
from src.publish_date import PublishDateFetcher
from src.utils import parse_facebook_date


@dataclass
class PendingPublishDateNote:
    path: Path
    video_id: str
    url: str


def _published_date_from_metadata(metadata: dict) -> date | None:
    raw = metadata.get("Published Date")
    if raw is None:
        return None
    text = str(raw).strip().strip('"').strip("'")
    if not text:
        return None
    return parse_facebook_date(text)


def _metadata_from_note(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    split = _split_frontmatter(content)
    if split is None:
        return {}

    block, _body = split
    try:
        post = frontmatter.loads(content)
        metadata = {
            key: _clean_field_value(str(post.metadata.get(key, "") or ""))
            for key in FRONTMATTER_KEYS
        }
    except Exception:
        metadata = _parse_frontmatter_block(block)

    for key in FRONTMATTER_KEYS:
        metadata.setdefault(key, "")
    return metadata


def list_notes_missing_publish_date(vault_dir: Path) -> list[PendingPublishDateNote]:
    pending: list[PendingPublishDateNote] = []

    for path in sorted(vault_dir.glob("*.md")):
        try:
            post = frontmatter.load(path)
            metadata = post.metadata
        except Exception:
            metadata = _metadata_from_note(path)

        if _published_date_from_metadata(metadata):
            continue

        video_id = _video_id_from_note(path)
        url = str(metadata.get("URL") or "").strip().strip('"').strip("'")
        if not video_id or not url:
            continue

        pending.append(PendingPublishDateNote(path=path, video_id=video_id, url=url))

    return pending


def update_note_published_date(path: Path, published_date: date) -> None:
    content = path.read_text(encoding="utf-8")
    repaired = repair_note_content(content)
    if repaired is not None:
        content = repaired

    split = _split_frontmatter(content)
    if split is None:
        raise RuntimeError(f"Could not parse frontmatter in {path}")

    block, body = split
    try:
        post = frontmatter.loads(content)
        metadata = {
            key: _clean_field_value(str(post.metadata.get(key, "") or ""))
            for key in FRONTMATTER_KEYS
        }
    except Exception:
        metadata = _parse_frontmatter_block(block)

    for key in FRONTMATTER_KEYS:
        metadata.setdefault(key, "")

    metadata["Published Date"] = published_date.isoformat()
    path.write_text(
        f"{_render_frontmatter(metadata)}\n{_normalize_body(body)}",
        encoding="utf-8",
    )


def _pending_to_video_record(note: PendingPublishDateNote, metadata: dict[str, str]) -> VideoRecord:
    accessed = parse_facebook_date(str(metadata.get("Accessed Date", ""))) or date.today()
    return VideoRecord(
        accessed_date=accessed,
        published_date=None,
        author=_clean_field_value(str(metadata.get("Author", "")).strip("[]")),
        channel=_clean_field_value(str(metadata.get("Channel", "")).strip("[]")),
        title=metadata.get("Title", ""),
        url=note.url,
        embed_url=str(metadata.get("Embed URL", "")),
        source=str(metadata.get("Source", "")),
        type=str(metadata.get("Type", "")),
        video_id=note.video_id,
        extraction_type=str(metadata.get("Extraction Type", "")),
    )


def backfill_publish_dates(
    vault_dir: Path,
    settings: Settings,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    pending = list_notes_missing_publish_date(vault_dir)
    if limit is not None:
        pending = pending[:limit]

    total = len(pending)
    print(f"Notes missing Published Date: {total}", flush=True)
    if total == 0:
        return 0, 0, 0

    if dry_run:
        for index, note in enumerate(pending[:10], start=1):
            print(f"  [{index}] {note.video_id} — {note.path.name[:80]}", flush=True)
        if total > 10:
            print(f"  ... and {total - 10} more", flush=True)
        return total, 0, 0

    fetcher = PublishDateFetcher(settings)
    updated = 0
    not_found = 0

    try:
        for index, note in enumerate(pending, start=1):
            metadata = _metadata_from_note(note.path)
            title = metadata.get("Title", "")
            if title.lower() in {"none", "null"}:
                title = note.path.stem
            video = _pending_to_video_record(note, metadata)
            print(
                f"[{index}/{total}] {note.video_id} — {title[:70]}",
                flush=True,
            )
            published_date = fetcher.fetch_date(video)
            if published_date:
                update_note_published_date(note.path, published_date)
                updated += 1
                print(f"  Published: {published_date.isoformat()}", flush=True)
            else:
                not_found += 1
                print("  Published: (not found)", flush=True)
    finally:
        fetcher.close()

    return total, updated, not_found


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Backfill missing Published Date fields in Obsidian notes."
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Obsidian vault folder (defaults to OBSIDIAN_VAULT_DIR).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N notes missing a publish date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List notes that would be processed without fetching or writing.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    vault_dir = args.vault or settings.obsidian_vault_dir
    if not vault_dir.exists():
        print(f"Vault folder not found: {vault_dir}", file=sys.stderr)
        return 1

    total, updated, not_found = backfill_publish_dates(
        vault_dir,
        settings,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print(f"Would process {total} note(s).", flush=True)
    else:
        print(
            f"\nDone. Processed {total}, updated {updated}, not found {not_found}.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

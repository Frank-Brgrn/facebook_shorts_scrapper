from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from src.config import PROJECT_ROOT, get_settings
from src.csv_export import export_csv
from src.obsidian_export import export_obsidian_notes, load_existing_vault_videos
from src.publish_date import enrich_publish_dates
from src.reel_extract import extract_reels_from_html_file, extracted_reel_to_record
from src.utils import find_latest_html_dump


def _resolve_html_path(html_file: Path | None, settings) -> Path | None:
    if html_file is not None:
        return html_file if html_file.is_absolute() else PROJECT_ROOT / html_file

    if settings.html_dump_file is not None:
        return settings.html_dump_file

    return find_latest_html_dump(settings.html_dumps_dir)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Import saved Facebook Reels from an HTML dump into CSV and Obsidian."
    )
    parser.add_argument(
        "--html-file",
        type=Path,
        help="HTML dump to parse (default: newest .html file in html dumps folder).",
    )
    parser.add_argument(
        "--no-fetch-dates",
        action="store_true",
        help="Skip Chrome publish-date lookup for new videos.",
    )
    args = parser.parse_args()

    html_path = _resolve_html_path(args.html_file, settings)
    if html_path is None or not html_path.exists():
        print("HTML dump not found.", flush=True)
        print(f"Save a Facebook Saved Reels HTML file into: {settings.html_dumps_dir}", flush=True)
        print("Example: html dumps/20260621 - Facebook Reels.html", flush=True)
        return 1

    print("Facebook Reels Importer", flush=True)
    print(f"Input: {html_path}", flush=True)
    print(flush=True)

    reels = extract_reels_from_html_file(html_path)
    print(f"Extracted {len(reels)} reel(s) from HTML.", flush=True)

    if not reels:
        print("No reels found in the HTML file.")
        return 1

    videos = [
        extracted_reel_to_record(
            reel,
            accessed_date=date.today(),
            source_label=settings.source_label,
            video_type=settings.video_type,
            extraction_type=settings.extraction_type,
        )
        for reel in reels
    ]

    for index, video in enumerate(videos[:5], start=1):
        print(f"  [{index}] {video.title[:80]}", flush=True)
    if len(videos) > 5:
        print(f"  ... and {len(videos) - 5} more", flush=True)

    existing = load_existing_vault_videos(settings.obsidian_vault_dir)
    new_videos = [video for video in videos if not existing.contains(video)]
    print(
        f"\nObsidian vault already contains {len(existing.normalized_urls)} video URL(s).",
        flush=True,
    )
    print(f"New videos to add: {len(new_videos)}", flush=True)

    fetch_dates = settings.fetch_publish_dates and not args.no_fetch_dates
    if fetch_dates and new_videos:
        print(
            f"\nFetching publish dates for {len(new_videos)} new video(s) via Chrome in background...",
            flush=True,
        )
        updated = enrich_publish_dates(new_videos, settings)
        print(f"Publish dates found for {updated} of {len(new_videos)} new video(s).", flush=True)
    elif new_videos:
        print("\nSkipping publish date lookup (--no-fetch-dates).", flush=True)

    csv_path = export_csv(videos, settings)
    note_paths, skipped = export_obsidian_notes(videos, settings)

    print(f"\nSaved {len(videos)} video(s) to CSV:")
    print(f"  {csv_path}")
    print(f"\nCreated {len(note_paths)} new Obsidian note(s):")
    for path in note_paths:
        print(f"  {path}")

    if skipped:
        print(
            f"\nSkipped {skipped} video(s) already present in Obsidian "
            "(matched by URL or video ID)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

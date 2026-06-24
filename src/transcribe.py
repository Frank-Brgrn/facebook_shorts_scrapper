from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from datetime import date

import frontmatter
import yt_dlp
from faster_whisper import WhisperModel
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import PROJECT_ROOT, Settings, get_settings
from src.models import VideoRecord, build_watch_url
from src.obsidian_export import _video_id_from_note
from src.utils import extract_video_id, normalize_facebook_video_url

TRANSCRIPT_SECTION_RE = re.compile(
    r"(# Transcript\r?\n)(.*?)(\r?\n---)",
    re.DOTALL,
)
IS_TRANSCRIBED_RE = re.compile(r"^Is Transcribed:\s*.*$", re.M)
URL_LINE_RE = re.compile(r"^URL:\s*(https://\S+)\s*$", re.M)
CORRUPT_FRONTMATTER_RE = re.compile(r"^Accessed Date:.*Author:", re.M)


@dataclass(frozen=True)
class PendingNote:
    path: Path
    video_id: str
    url: str
    mark_only: bool = False


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _is_transcribed_flag(metadata: dict) -> bool:
    value = metadata.get("Is Transcribed")
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def extract_transcript_text(content: str) -> str:
    match = TRANSCRIPT_SECTION_RE.search(content)
    if not match:
        return ""
    return match.group(2).strip()


def _read_note_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _url_from_note_text(text: str, video_id: str) -> str:
    match = URL_LINE_RE.search(text)
    if match:
        return match.group(1).strip()
    return build_watch_url(video_id)


def _is_transcribed_text(text: str) -> bool:
    match = IS_TRANSCRIBED_RE.search(text)
    if not match:
        return False
    value = match.group(0).split(":", 1)[1].strip().strip('"').strip("'")
    return value.lower() in {"1", "true", "yes"}


def _note_is_transcribed(path: Path) -> bool:
    try:
        text = _read_note_text(path)
    except OSError:
        return False
    return _is_transcribed_text(text) and bool(extract_transcript_text(text))


def _insert_is_transcribed(text: str, value: int = 1) -> str:
    line = f"Is Transcribed: {value}"
    if re.search(rf"^Is Transcribed:\s*{value}\s*$", text, re.M):
        return text
    if IS_TRANSCRIBED_RE.search(text):
        return IS_TRANSCRIBED_RE.sub(line, text, count=1)
    return re.sub(
        r"\A(---\r?\n(?:.*?\r?\n)*?)(---\r?\n)",
        rf"\1{line}\n\2",
        text,
        count=1,
        flags=re.S,
    )


def _apply_transcript(text: str, transcript: str) -> str:
    match = TRANSCRIPT_SECTION_RE.search(text)
    if not match:
        raise RuntimeError("Could not find # Transcript section")
    return text[: match.start(2)] + transcript.strip() + text[match.end(2) :]


def reset_false_transcribed_flags(vault_dir: Path) -> int:
    reset = 0
    for path in sorted(vault_dir.glob("*.md")):
        try:
            text = _read_note_text(path)
        except OSError:
            continue
        if extract_transcript_text(text) or not _is_transcribed_text(text):
            continue
        text = IS_TRANSCRIBED_RE.sub('Is Transcribed: ""', text, count=1)
        path.write_text(text, encoding="utf-8")
        reset += 1
    return reset


def update_obsidian_note(note_path: Path, transcript: str | None = None) -> None:
    text = _read_note_text(note_path)
    if transcript is not None:
        text = _apply_transcript(text, transcript)
    text = _insert_is_transcribed(text, 1)
    note_path.write_text(text, encoding="utf-8")


def _latest_csv_path() -> Path | None:
    csv_dir = get_settings().scrapped_files_dir
    candidates = sorted(csv_dir.glob("* - Facebook Reels Scrapped.csv"))
    return candidates[-1] if candidates else None


def _load_csv_by_video_id(csv_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            video_id = (row.get("Video ID") or "").strip()
            if video_id:
                rows[video_id] = row
    return rows


def _record_from_csv_row(row: dict[str, str], *, transcript: str = "") -> VideoRecord:
    accessed_raw = (row.get("Accessed Date") or "").strip()
    published_raw = (row.get("Published Date") or "").strip()
    return VideoRecord(
        accessed_date=date.fromisoformat(accessed_raw) if accessed_raw else date.today(),
        published_date=date.fromisoformat(published_raw) if published_raw else None,
        author=(row.get("Author") or "").strip(),
        channel=(row.get("Channel") or "").strip(),
        title=(row.get("Title") or "").strip(),
        url=(row.get("URL") or "").strip(),
        embed_url=(row.get("Embed URL") or "").strip(),
        source=(row.get("Source") or "").strip(),
        type=(row.get("Type") or "").strip(),
        video_id=(row.get("Video ID") or "").strip(),
        extraction_type=(row.get("Extraction Type") or "").strip(),
        summary=(row.get("Summary") or "").strip(),
        topic=(row.get("Topic") or "").strip(),
        tags=(row.get("Tags") or "").strip(),
        status=(row.get("Status") or "").strip(),
        is_useful=(row.get("Is Useful") or "").strip(),
        is_transcribed="1" if transcript else "",
        is_ai_analyzed=(row.get("Is AI Analyzed") or "").strip(),
        rating=(row.get("Rating") or "").strip(),
        transcript=transcript,
    )


def _render_note(record: VideoRecord, settings: Settings) -> str:
    env = Environment(
        loader=FileSystemLoader(settings.template_path.parent),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(settings.template_path.name)
    return template.render(v=record.to_template_context())


def rebuild_note_from_csv(
    path: Path,
    *,
    csv_index: dict[str, dict[str, str]],
    settings: Settings,
    transcript: str,
) -> None:
    video_id = _video_id_from_note(path)
    if not video_id:
        raise ValueError(f"No video ID found in {path.name}")

    row = csv_index.get(video_id)
    if row is None:
        raise ValueError(f"No CSV row found for video ID {video_id}")

    record = _record_from_csv_row(row, transcript=transcript)
    path.write_text(_render_note(record, settings), encoding="utf-8")


def repair_corrupted_obsidian_notes(vault_dir: Path) -> int:
    settings = get_settings()
    csv_path = _latest_csv_path()
    csv_index = _load_csv_by_video_id(csv_path) if csv_path else {}
    git_root = vault_dir.parent.parent.parent
    repaired = 0

    for path in sorted(vault_dir.glob("*.md")):
        try:
            text = _read_note_text(path)
        except OSError:
            continue
        if not CORRUPT_FRONTMATTER_RE.search(text):
            continue

        transcript = extract_transcript_text(text)
        rel_path = path.relative_to(git_root)
        checkout = subprocess.run(
            ["git", "checkout", "--", str(rel_path)],
            cwd=git_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if checkout.returncode == 0:
            if transcript:
                update_obsidian_note(path, transcript)
            else:
                update_obsidian_note(path)
        elif csv_index:
            rebuild_note_from_csv(
                path,
                csv_index=csv_index,
                settings=settings,
                transcript=transcript,
            )
        else:
            err = (checkout.stderr or checkout.stdout or "unknown git error").strip()
            print(f"Could not restore {path.name}: {err}", flush=True)
            continue

        repaired += 1
        print(f"Repaired: {path.name}", flush=True)
    return repaired


def count_transcribed_notes(vault_dir: Path) -> int:
    if not vault_dir.exists():
        return 0
    return sum(1 for path in vault_dir.glob("*.md") if _note_is_transcribed(path))


def list_pending_obsidian_notes(vault_dir: Path) -> tuple[list[PendingNote], list[PendingNote]]:
    if not vault_dir.exists():
        return [], []

    to_transcribe: list[PendingNote] = []
    to_mark: list[PendingNote] = []

    for path in sorted(vault_dir.glob("*.md")):
        if _note_is_transcribed(path):
            continue

        video_id = _video_id_from_note(path)
        if not video_id:
            continue

        try:
            text = _read_note_text(path)
        except OSError:
            continue

        url = _url_from_note_text(text, video_id)
        transcript = extract_transcript_text(text)

        pending = PendingNote(path=path, video_id=video_id, url=url)
        if transcript:
            to_mark.append(pending)
        else:
            to_transcribe.append(pending)

    return to_transcribe, to_mark


def _download_audio(
    url: str,
    output_dir: Path,
    *,
    cookies_browser: str | None,
    reuse_existing: bool = True,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    video_id = extract_video_id(url) or "audio"

    if reuse_existing:
        existing = sorted(output_dir.glob(f"{video_id}.*"))
        if existing:
            return existing[0]

    output_template = str(output_dir / f"{video_id}.%(ext)s")
    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if cookies_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_browser,)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded = Path(ydl.prepare_filename(info))

    if downloaded.exists():
        return downloaded

    matches = sorted(output_dir.glob(f"{video_id}.*"))
    if not matches:
        raise RuntimeError(f"Download finished but no audio file was found for {url}")
    return matches[0]


AUDIO_EXTENSIONS = {".m4a", ".mp4", ".webm", ".mp3", ".wav", ".opus", ".mkv"}


def _delete_audio_file(path: Path) -> None:
    for candidate in path.parent.glob(f"{path.stem}.*"):
        if candidate.suffix.lower() in AUDIO_EXTENSIONS and candidate.exists():
            candidate.unlink()


def cleanup_transcribed_audio(vault_dir: Path, work_dir: Path) -> int:
    if not work_dir.exists():
        return 0

    transcribed_ids = {
        _video_id_from_note(note)
        for note in vault_dir.glob("*.md")
        if _note_is_transcribed(note) and _video_id_from_note(note)
    }

    removed = 0
    for path in work_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if path.stem in transcribed_ids:
            _delete_audio_file(path)
            removed += 1
    return removed


class BatchTranscriber:
    def __init__(
        self,
        *,
        model_name: str = "small",
        language: str | None = None,
        work_dir: Path,
        cookies_browser: str | None = None,
    ) -> None:
        self.work_dir = work_dir
        self.language = language
        self.cookies_browser = cookies_browser
        print(f"Loading faster-whisper model ({model_name})...", flush=True)
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe_url(self, url: str) -> tuple[str, Path]:
        normalized = normalize_facebook_video_url(url)
        if not normalized:
            raise ValueError(f"Not a Facebook video URL: {url}")

        audio_path = _download_audio(
            normalized,
            self.work_dir,
            cookies_browser=self.cookies_browser,
        )
        segments, info = self.model.transcribe(
            str(audio_path),
            language=self.language,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        print(
            f"  Detected language: {info.language} ({info.language_probability:.0%})",
            flush=True,
        )
        return text, audio_path


def load_urls_from_csv(csv_path: Path, *, limit: int | None = None) -> list[str]:
    urls: list[str] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            url = (row.get("URL") or "").strip()
            if url:
                urls.append(url)
            if limit is not None and len(urls) >= limit:
                break
    return urls


def run_obsidian_batch(
    *,
    vault_dir: Path,
    work_dir: Path,
    model_name: str,
    language: str | None,
    cookies_browser: str | None,
    limit: int | None,
) -> int:
    to_transcribe, to_mark = list_pending_obsidian_notes(vault_dir)
    pending_total = len(to_transcribe)
    already_done = count_transcribed_notes(vault_dir)

    if limit is not None:
        if limit < 1:
            raise ValueError("Count must be at least 1")
        to_transcribe = to_transcribe[:limit]

    print(f"Obsidian vault: {vault_dir}", flush=True)
    print(f"Already transcribed (skipped): {already_done}", flush=True)
    print(f"Pending transcription: {pending_total}", flush=True)
    print(f"Processing this run: {len(to_transcribe)}", flush=True)
    if to_mark:
        print(f"Notes with transcript text to flag only: {len(to_mark)}", flush=True)

    removed = cleanup_transcribed_audio(vault_dir, work_dir)
    if removed:
        print(f"Removed {removed} cached audio file(s) for already-transcribed notes.", flush=True)

    for note in to_mark:
        update_obsidian_note(note.path)
        print(f"Marked existing transcript: {note.path.name}", flush=True)

    if not to_transcribe:
        print("Nothing left to transcribe.", flush=True)
        return 0

    transcriber = BatchTranscriber(
        model_name=model_name,
        language=language,
        work_dir=work_dir,
        cookies_browser=cookies_browser,
    )

    failures = 0
    for index, note in enumerate(to_transcribe, start=1):
        print(f"\n[{index}/{len(to_transcribe)}] {note.path.name}", flush=True)
        print(f"  Video ID: {note.video_id}", flush=True)
        try:
            transcript, audio_path = transcriber.transcribe_url(note.url)
            update_obsidian_note(note.path, transcript)
            _delete_audio_file(audio_path)
            print(f"  Saved transcript ({len(transcript)} chars)", flush=True)
        except Exception as exc:
            failures += 1
            print(f"  Error: {exc}", flush=True)

    print(
        f"\nDone. Transcribed {len(to_transcribe) - failures}/{len(to_transcribe)} note(s).",
        flush=True,
    )
    if failures:
        print(f"Failed: {failures}", flush=True)
    return 1 if failures else 0


def main() -> int:
    _ensure_utf8_stdout()
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Transcribe Facebook Reel audio.")
    parser.add_argument(
        "--obsidian",
        action="store_true",
        help="Transcribe all Obsidian notes missing a transcript (default mode).",
    )
    parser.add_argument("--url", help="Facebook watch URL to transcribe")
    parser.add_argument("--video-id", help="Facebook video ID to transcribe")
    parser.add_argument(
        "--csv",
        type=Path,
        help="CSV export to read URLs from (uses the URL column)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of pending notes to transcribe (same as COUNT)",
    )
    parser.add_argument(
        "count",
        nargs="?",
        type=int,
        metavar="COUNT",
        help="Number of pending notes to transcribe (default: all pending)",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="faster-whisper model size (default: small)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force language code, e.g. fr or en (default: auto-detect)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=PROJECT_ROOT / "_transcript_work",
        help="Folder for downloaded audio files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional text file to save the transcript (single URL mode only)",
    )
    parser.add_argument(
        "--reset-false-flags",
        action="store_true",
        help="Clear Is Transcribed on notes that have no transcript text.",
    )
    parser.add_argument(
        "--repair-corrupted",
        action="store_true",
        help="Restore corrupted Obsidian frontmatter from git and keep transcripts.",
    )
    parser.add_argument(
        "--cookies-browser",
        default=None,
        help="Browser for yt-dlp cookies, e.g. chrome or edge (optional)",
    )
    args = parser.parse_args()

    if args.limit is not None and args.count is not None:
        parser.error("Use either COUNT or --limit, not both")

    note_limit = args.limit if args.limit is not None else args.count

    if args.repair_corrupted:
        repaired = repair_corrupted_obsidian_notes(settings.obsidian_vault_dir)
        print(f"Repaired {repaired} note(s).", flush=True)
        return 0

    if args.reset_false_flags:
        reset = reset_false_transcribed_flags(settings.obsidian_vault_dir)
        print(f"Reset {reset} false Is Transcribed flag(s).", flush=True)
        return 0

    if args.obsidian or not any([args.url, args.video_id, args.csv]):
        try:
            return run_obsidian_batch(
                vault_dir=settings.obsidian_vault_dir,
                work_dir=args.work_dir,
                model_name=args.model,
                language=args.language,
                cookies_browser=args.cookies_browser,
                limit=note_limit,
            )
        except ValueError as exc:
            print(f"Error: {exc}", flush=True)
            return 1

    urls: list[str] = []
    if args.url:
        urls = [args.url]
    elif args.video_id:
        urls = [build_watch_url(args.video_id)]
    elif args.csv:
        csv_path = args.csv if args.csv.is_absolute() else PROJECT_ROOT / args.csv
        if not csv_path.exists():
            print(f"CSV not found: {csv_path}", flush=True)
            return 1
        urls = load_urls_from_csv(csv_path, limit=note_limit)

    transcriber = BatchTranscriber(
        model_name=args.model,
        language=args.language,
        work_dir=args.work_dir,
        cookies_browser=args.cookies_browser,
    )

    exit_code = 0
    transcripts: list[tuple[str, str]] = []

    for index, url in enumerate(urls, start=1):
        video_id = extract_video_id(url) or f"video_{index}"
        print(f"\n[{index}/{len(urls)}] Video ID {video_id}", flush=True)
        try:
            transcript, audio_path = transcriber.transcribe_url(url)
        except Exception as exc:
            print(f"Error: {exc}", flush=True)
            exit_code = 1
            continue

        transcripts.append((video_id, transcript))
        print("\n--- Transcript ---", flush=True)
        print(transcript, flush=True)

        for path in settings.obsidian_vault_dir.glob("*.md"):
            if _video_id_from_note(path) == video_id:
                update_obsidian_note(path, transcript)
                _delete_audio_file(audio_path)
                print(f"Updated Obsidian note: {path}", flush=True)
                break

    if args.output and len(transcripts) == 1:
        output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(transcripts[0][1], encoding="utf-8")
        print(f"\nSaved transcript: {output_path}", flush=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

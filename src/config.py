from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_path(env_name: str, default: Path) -> Path:
    raw = os.getenv(env_name)
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _default_chrome_user_data_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"


@dataclass(frozen=True)
class Settings:
    html_dumps_dir: Path
    html_dump_file: Path | None
    scrapped_files_dir: Path
    obsidian_vault_dir: Path
    chrome_user_data_dir: Path
    chrome_automation_dir: Path
    chrome_profile_directory: str
    chrome_debug_port: int
    headless: bool
    fetch_publish_dates: bool
    extraction_type: str
    source_label: str
    video_type: str
    template_path: Path


def get_settings() -> Settings:
    html_dump_raw = os.getenv("FB_REELS_HTML")
    html_dump_file: Path | None = None
    if html_dump_raw:
        html_dump_file = Path(html_dump_raw)
        if not html_dump_file.is_absolute():
            html_dump_file = PROJECT_ROOT / html_dump_file

    return Settings(
        html_dumps_dir=_resolve_path("HTML_DUMPS_DIR", PROJECT_ROOT / "html dumps"),
        html_dump_file=html_dump_file,
        scrapped_files_dir=_resolve_path("SCRAPPED_FILES_DIR", PROJECT_ROOT / "scrapped files"),
        obsidian_vault_dir=_resolve_path(
            "OBSIDIAN_VAULT_DIR",
            Path(r"C:\PROJECTS-CODE\Vaults\Ideaverse\Atlas\Sources\Facebook Reels"),
        ),
        chrome_user_data_dir=Path(
            os.getenv("CHROME_USER_DATA_DIR", str(_default_chrome_user_data_dir()))
        ),
        chrome_automation_dir=_resolve_path(
            "CHROME_AUTOMATION_DIR", PROJECT_ROOT / "chrome_automation"
        ),
        chrome_profile_directory=os.getenv("CHROME_PROFILE_DIRECTORY", "Default"),
        chrome_debug_port=int(os.getenv("CHROME_DEBUG_PORT", "9222")),
        headless=os.getenv("HEADLESS", "true").lower() in {"1", "true", "yes"},
        fetch_publish_dates=os.getenv("FETCH_PUBLISH_DATES", "true").lower()
        in {"1", "true", "yes"},
        extraction_type=os.getenv("EXTRACTION_TYPE", "Facebook Shorts Scraper"),
        source_label=os.getenv("SOURCE_LABEL", "Facebook Reel"),
        video_type=os.getenv("VIDEO_TYPE", "Short Video"),
        template_path=PROJECT_ROOT / "templates" / "obsidian_note.md.j2",
    )

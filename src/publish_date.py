from __future__ import annotations

import time

from datetime import date

from src.browser import ChromeSession
from src.chrome_utils import ensure_chrome_closed
from src.config import Settings
from src.models import VideoRecord
from src.utils import parse_publish_date

EXTRACT_PUBLISH_DATE_SCRIPT = """
() => {
  const metaSelectors = [
    'meta[property="article:published_time"]',
    'meta[property="og:published_time"]',
    'meta[name="datePublished"]',
  ];
  for (const sel of metaSelectors) {
    const el = document.querySelector(sel);
    if (el && el.content) {
      return el.content;
    }
  }

  const html = document.documentElement.innerHTML;
  const patterns = [
    /"datePublished"\\s*:\\s*"([^"]+)"/,
    /"publish_time"\\s*:\\s*(\\d{10,13})/,
    /"creation_time"\\s*:\\s*(\\d{10,13})/,
    /"uploaded"\\s*:\\s*(\\d{10,13})/,
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return null;
}
"""


class PublishDateFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        ensure_chrome_closed()
        self.session = ChromeSession.open(settings)

    def close(self) -> None:
        self.session.disconnect()

    def _reconnect(self) -> None:
        print("    Reconnecting Chrome...", flush=True)
        try:
            self.session.disconnect()
        except Exception:
            pass
        ensure_chrome_closed()
        self.session = ChromeSession.open(self.settings)

    @staticmethod
    def _is_browser_closed_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "browser has been closed" in message or "target page, context or browser has been closed" in message

    def fetch_date(self, video: VideoRecord) -> date | None:
        for attempt in range(2):
            try:
                self.session.goto(video.url)
                time.sleep(1.5)
                raw = self.session.evaluate(EXTRACT_PUBLISH_DATE_SCRIPT)
                return parse_publish_date(raw)
            except Exception as exc:
                if attempt == 0 and self._is_browser_closed_error(exc):
                    self._reconnect()
                    continue
                print(f"    Warning: could not fetch date for {video.video_id}: {exc}", flush=True)
                return None
        return None

    def enrich_videos(self, videos: list[VideoRecord]) -> int:
        updated = 0
        total = len(videos)

        for index, video in enumerate(videos, start=1):
            if video.published_date:
                continue

            print(f"  [{index}/{total}] {video.video_id} — {video.title[:70]}", flush=True)
            published_date = self.fetch_date(video)
            if published_date:
                video.published_date = published_date
                updated += 1
                print(f"    Published: {published_date.isoformat()}", flush=True)
            else:
                print("    Published: (not found)", flush=True)

        return updated


def enrich_publish_dates(videos: list[VideoRecord], settings: Settings) -> int:
    if not videos:
        return 0

    fetcher = PublishDateFetcher(settings)
    try:
        return fetcher.enrich_videos(videos)
    finally:
        fetcher.close()

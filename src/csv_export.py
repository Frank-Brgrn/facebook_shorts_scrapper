from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import Settings
from src.models import CSV_COLUMNS, VideoRecord


def export_csv(videos: list[VideoRecord], settings: Settings) -> Path:
    settings.scrapped_files_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = settings.scrapped_files_dir / f"{timestamp} - Facebook Reels Scrapped.csv"

    rows = [video.to_csv_row() for video in videos]
    dataframe = pd.DataFrame(rows, columns=CSV_COLUMNS)
    dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path

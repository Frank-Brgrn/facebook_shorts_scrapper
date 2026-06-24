# Facebook Reels Scraper

Import saved Facebook Reels from a browser HTML dump into CSV and Obsidian, optionally fetch publish dates, and transcribe video audio into your notes.

Repository: [github.com/Frank-Brgrn/facebook_shorts_scrapper](https://github.com/Frank-Brgrn/facebook_shorts_scrapper)

## What it does

1. **Import** — Parse a Saved Reels page HTML export and extract metadata (title, author, URL, video ID).
2. **Export CSV** — Write a timestamped CSV under `scrapped files/`.
3. **Export Obsidian** — Create one note per **new** video in your vault (skips duplicates by video ID / URL).
4. **Publish dates** — For new videos only, open each page in Chrome (background) and try to read the publish date.
5. **Transcribe** — Download audio with yt-dlp, transcribe with faster-whisper, write text into the note and set `Is Transcribed: 1`.

There is **no live scraping** of the Facebook saved page. You refresh an HTML dump manually in Chrome, then run the importer.

## Prerequisites

- Windows
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (used by the batch scripts)
- Google Chrome with an active Facebook login (for publish-date lookup and some video downloads)
- **ffmpeg** (for transcription — installed automatically by the setup script below)

## Setup

### 1. Create the conda environment

From the project root, run **once**:

```bat
_setup_env\ADMIN_Install_Env.bat
```

This creates the `facebook_shorts_scrapper` conda env (Python 3.13), installs pip dependencies from `_setup_env\requirements.txt`, and installs **ffmpeg** for transcription.

### 2. Configure paths

Copy the example env file and edit paths if needed:

```bat
copy .env.example .env
```

Key settings in `.env`:

| Variable | Purpose |
|----------|---------|
| `SCRAPPED_FILES_DIR` | Folder for CSV exports |
| `HTML_DUMPS_DIR` | Folder for Saved Reels HTML files |
| `OBSIDIAN_VAULT_DIR` | Obsidian vault folder for reel notes |
| `FETCH_PUBLISH_DATES` | `true` / `false` — Chrome lookup for new videos |
| `HEADLESS` | `true` — Chrome runs in the background |

### 3. Refresh dependencies (optional)

After `requirements.txt` changes:

```bat
_setup_env\ADMIN_Install_Requirements.bat
```

### 4. Remove environment (optional)

```bat
_setup_env\ADMIN_Remove_Env.bat
```

## Typical workflow

### Step 1 — Save the Facebook page as HTML

1. Open [Saved Reels](https://www.facebook.com/saved/?dashboard_section=REELS) in Chrome and log in.
2. Scroll to the bottom until all reels are loaded.
3. Save the full page HTML into `html dumps/`, e.g. `html dumps/20260621 - Facebook Reels.html`.

The importer uses the **newest** `.html` file in that folder by default.

### Step 2 — Import into CSV + Obsidian

```bat
run_scraper.bat
```

### Step 3 — Transcribe notes (optional)

```bat
run_transcribe.bat 10
run_transcribe.bat
run_transcribe.bat --limit 10
```

Processes pending Obsidian notes only. Notes that already have `Is Transcribed: 1` **and** transcript text are skipped. Downloaded audio is deleted after each successful note.

### Step 4 — Backfill missing publish dates (optional)

```bat
run_backfill_dates.bat
```

Fills `Published Date` on existing notes that are still empty.

## Batch files reference

All workflow scripts activate conda env `facebook_shorts_scrapper` and forward extra arguments to the underlying Python module.

### Root scripts (daily use)

| File | Purpose |
|------|---------|
| **`run_scraper.bat`** | Import reels from the newest HTML dump (or `--html-file`). Exports CSV + new Obsidian notes. Fetches publish dates for new videos unless `--no-fetch-dates` is passed. |
| **`run_transcribe.bat`** | Transcribe pending Obsidian notes. Pass a number: `run_transcribe.bat 10` (or `--limit 10`). Omit the number to process all pending. Skips notes already transcribed. |
| **`run_backfill_dates.bat`** | Fill missing `Published Date` in Obsidian frontmatter via Chrome. Examples: `--dry-run`, `--limit 5`. |

### Setup scripts (`_setup_env/`)

| File | Purpose |
|------|---------|
| **`ADMIN_Install_Env.bat`** | One-time setup: create conda env, install Python packages, install ffmpeg. |
| **`ADMIN_Install_Requirements.bat`** | Reinstall / upgrade packages from `requirements.txt` into the existing env. |
| **`ADMIN_Remove_Env.bat`** | Delete the `facebook_shorts_scrapper` conda environment. |

## Command-line examples

```bat
run_scraper.bat --no-fetch-dates
run_scraper.bat --html-file "html dumps/20260621 - Facebook Reels.html"

run_transcribe.bat --limit 10
run_transcribe.bat --video-id 1443970823862051

run_backfill_dates.bat --dry-run

python -m src.obsidian_repair
python -m src.obsidian_repair --dry-run
```

## Project layout

```
facebook_shorts_scrapper/
├── run_scraper.bat          # Import HTML → CSV + Obsidian
├── run_transcribe.bat       # Whisper transcription
├── run_backfill_dates.bat   # Publish date backfill
├── _setup_env/              # Conda setup scripts + requirements.txt
├── src/                     # Python source
├── templates/               # Obsidian note Jinja template
├── _docs/spec.md            # Full project specification
├── html dumps/              # Your HTML exports (gitignored)
├── scrapped files/          # CSV exports (gitignored)
├── _transcript_work/        # Temporary audio during transcription (gitignored)
└── chrome_automation/       # Chrome profile for automation (gitignored)
```

## Gitignored data (not in the repository)

These folders are local working data only:

- `html dumps/` — Facebook page HTML exports
- `scrapped files/*.csv` — CSV export history
- `_transcript_work/` — temporary audio while transcribing
- `_transcript_test/` — local transcription tests
- `chrome_automation/` — Chrome user data for publish-date / download
- `.env` — your personal paths and secrets

## Obsidian note format

Each note includes YAML frontmatter (same fields as the CSV, plus `Is Transcribed`), an embedded Facebook iframe, structured note sections, and a `# Transcript` block filled by `run_transcribe.bat`.

See [`_docs/spec.md`](_docs/spec.md) for the full field list, duplicate-detection rules, and frontmatter details.

## Maintenance

**Repair broken Obsidian frontmatter** (red properties in Obsidian — usually invalid YAML from old multi-line titles):

```bat
python -m src.obsidian_repair
python -m src.obsidian_repair --dry-run
```

**Reset false transcription flags** (notes marked transcribed but with an empty transcript):

```bat
python -m src.transcribe --reset-false-flags
```

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| No HTML file found | Add a `.html` file under `html dumps/` or set `FB_REELS_HTML` in `.env`. |
| Facebook login required | Set `HEADLESS=false` in `.env`, run the scraper once, log in in Chrome, then set `HEADLESS=true` again. |
| Transcription download fails | Pass `--cookies-browser chrome` to `run_transcribe.bat` (close Chrome first). |
| Slow bulk transcription | ~20–30 s per reel on CPU; use `--limit N` to test first. |

## License

Private / personal tooling — adjust as needed for your use.

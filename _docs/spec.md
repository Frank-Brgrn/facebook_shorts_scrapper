# Facebook Reels Importer — Project Spec

## Overview

The objective is to import all videos saved on Facebook and archive them in CSV and Obsidian.

The workflow always starts from a saved HTML dump of the Facebook Saved Reels page, stored in the `html dumps` folder. There is no live page scraping.

For new videos only, Chrome runs in the background to try to fetch each video's publish date from Facebook.

## Setup

- Conda environment: `facebook_shorts_scrapper`
- Copy `.env.example` to `.env` and adjust paths if needed
- Default Obsidian vault folder:  
  `C:\PROJECTS-CODE\Vaults\Ideaverse\Atlas\Sources\Facebook Reels`

## Workflow

### 1. Refresh the HTML source

1. Open Facebook in Chrome and log in if not already.
2. Go to Saved Reels:  
   `https://www.facebook.com/saved/?dashboard_section=REELS`
3. Scroll to the bottom so all saved reels are loaded.
4. Save the full page HTML into the `html dumps` folder with a date in the filename, for example:  
   `html dumps/20260621 - Facebook Reels.html`

The importer uses the **newest** `.html` file in that folder by default.

### 2. Run the importer

Run:

```bat
run_scraper.bat
```

Or:

```bat
python -m src.main
```

The script:

1. Parses the newest HTML dump from `html dumps` (or a file passed with `--html-file`)
2. Extracts reel metadata (title, author, URL, video ID, etc.)
3. Compares URLs against existing Obsidian notes and identifies new videos
4. For new videos only, opens Chrome in the background and tries to fetch the publish date from each video page
5. Exports a new CSV file
6. Creates Obsidian notes only for videos not already in the vault

Skip the Chrome publish-date step:

```bat
python -m src.main --no-fetch-dates
```

### 3. Publish date lookup (new videos only)

When new videos are found:

- Chrome launches in the background using your logged-in profile (`HEADLESS=true` by default)
- Each new video page is opened briefly
- The script tries to read the publish date from page metadata
- If no date is found, `Published Date` stays empty

Environment variables:

- `FETCH_PUBLISH_DATES=true` — enable/disable publish date lookup
- `HEADLESS=true` — run Chrome headless in the background
- `CHROME_PROFILE_DIRECTORY=Default` — Chrome profile with Facebook login

On first run, if Facebook requires login, temporarily set `HEADLESS=false`, log in in the Chrome window, then switch back to headless.

### 4. CSV export

- Each run writes a new CSV with all videos found in the current HTML file.
- **CSV naming:** `[datetime] - Facebook Reels Scrapped.csv`
- **CSV folder:** `scrapped files`
- **CSV columns:** Each row represents one video and includes:
  - Accessed Date
  - Published Date
  - Author
  - Channel
  - Title
  - URL
  - Embed URL
  - Source
  - Type (e.g., Short Video)
  - Video ID
  - Extraction Type
  - Summary (optional)
  - Topic (optional)
  - Tags (optional)
  - Status (optional)
  - Is Useful (optional)
  - Rating (optional)

### 5. Obsidian export (no duplicates)

Before creating any note, the script scans all existing notes in the vault and builds a list from:

- `URL`
- `Embed URL`
- `Video ID`

Each URL is normalized to a canonical form (`https://www.facebook.com/watch/?v=...`), so variants like `watch/?v=` and `watch/?ref=saved&v=` are treated as the same video.

When processing the HTML file:

- If a video URL or video ID already exists in the vault, it is skipped.
- Duplicates within the same HTML run are also skipped.
- Only genuinely new videos get a new note.

Console output includes:

- How many URLs are already in the vault
- How many new videos were found
- How many publish dates were fetched
- How many new notes were created
- How many videos were skipped as duplicates

**Note filename format:**  
`YYYYMMDD - [title].md`  
Example: `_docs\20260406 - Claude Code remplace les designers 😳 Commente “Design” et j.md`

If two different videos share the same title, the second file gets a `(2)` suffix. That is expected when the videos are different (different URL / video ID).

### 6. Obsidian note format

**Frontmatter:** Same fields as the CSV columns, plus `Is Transcribed`.

- All values are written as quoted JSON strings (valid YAML for Obsidian properties).
- Titles and text fields are collapsed to a single line (no line breaks in frontmatter).
- Author and Channel are stored as Obsidian wiki links, e.g. `"[[Channel Name]]"`.

Example structure:

```
---
Accessed Date: "2026-04-06"
Published Date: "2026-04-05"
Author: "[[IA Boss Officiel]]"
Channel: "[[IA Boss Officiel]]"
Title: "Claude Code remplace les designers 😳 Commente “Design” et j"
URL: "https://www.facebook.com/watch/?v=1443970823862051"
Embed URL: "https://www.facebook.com/watch/?ref=saved&v=1443970823862051"
Source: "Facebook Reel"
Type: "Short Video"
Video ID: "1443970823862051"
Extraction Type: "Facebook Shorts Scraper"
Summary: ""
Topic: ""
Tags: ""
Status: ""
Is Useful: ""
Rating: ""
Is Transcribed: ""
---
<iframe ...></iframe>

# Notes

## 🧠 Key Ideas
-

## 💬 Quotes Worth Keeping
-

## 📝 Detailed Notes
-

## 🧪 Action Items / Experiments
-

## 🔁 Links & Resources
-

---

# Transcript

---

# AI (Link files)
```

**Vault folder:**  
`C:\PROJECTS-CODE\Vaults\Ideaverse\Atlas\Sources\Facebook Reels`

### 7. Transcription (optional)

Run:

```bat
run_transcribe.bat
```

This transcribes Obsidian notes that do not yet have a transcript and sets `Is Transcribed: 1` in frontmatter.

Useful options:

- `run_transcribe.bat --limit 5` — test on first 5 notes
- `run_transcribe.bat --url "https://www.facebook.com/watch/?v=..."` — single video

### 8. Backfill missing publish dates

To fill `Published Date` on notes that already exist but are missing it:

```bat
run_backfill_dates.bat
```

Useful options:

- `run_backfill_dates.bat --dry-run` — list notes missing a publish date
- `run_backfill_dates.bat --limit 5` — test on first 5 notes

This opens Chrome in the background, visits each video page, and writes the date into frontmatter.

### 9. Repair broken frontmatter (maintenance)

If Obsidian properties appear in red, frontmatter YAML is likely invalid (often caused by multi-line titles in older notes).

Repair all notes in the vault:

```bat
python -m src.obsidian_repair
```

Preview changes without writing:

```bat
python -m src.obsidian_repair --dry-run
```

## Goals

- Automate organization and archiving of saved videos and their metadata.
- Import reels from a Facebook HTML dump only (no live scraping).
- Ensure no duplicate videos in Obsidian (matched by normalized URL or video ID).
- Enrich new videos with publish dates when Facebook exposes them.
- Keep a structured record of all saved Facebook Reels in CSV and Obsidian.
- Support optional transcription into Obsidian notes.

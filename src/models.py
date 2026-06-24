from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


CSV_COLUMNS = [
    "Accessed Date",
    "Published Date",
    "Author",
    "Channel",
    "Title",
    "URL",
    "Embed URL",
    "Source",
    "Type",
    "Video ID",
    "Extraction Type",
    "Summary",
    "Topic",
    "Tags",
    "Status",
    "Is Useful",
    "Is Transcribed",
    "Is AI Analyzed",
    "Rating",
]

OBSIDIAN_FRONTMATTER_KEYS = [
    "Accessed Date",
    "Published Date",
    "Author",
    "Channel",
    "Title",
    "URL",
    "Embed URL",
    "Source",
    "Type",
    "Video ID",
    "Summary",
    "Topic",
    "Tags",
    "Status",
    "Is Useful",
    "Is Transcribed",
    "Is AI Analyzed",
    "Rating",
]


@dataclass
class VideoRecord:
    accessed_date: date
    published_date: date | None
    author: str
    channel: str
    title: str
    url: str
    embed_url: str
    source: str
    type: str
    video_id: str
    extraction_type: str
    summary: str = ""
    topic: str = ""
    tags: str = ""
    status: str = ""
    is_useful: str = ""
    is_transcribed: str = ""
    is_ai_analyzed: str = ""
    rating: str = ""
    transcript: str = ""

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "Accessed Date": self.accessed_date.isoformat(),
            "Published Date": self.published_date.isoformat() if self.published_date else "",
            "Author": self.author,
            "Channel": self.channel,
            "Title": self.title,
            "URL": self.url,
            "Embed URL": self.embed_url,
            "Source": self.source,
            "Type": self.type,
            "Video ID": self.video_id,
            "Extraction Type": self.extraction_type,
            "Summary": self.summary,
            "Topic": self.topic,
            "Tags": self.tags,
            "Status": self.status,
            "Is Useful": self.is_useful,
            "Is Transcribed": self.is_transcribed,
            "Is AI Analyzed": self.is_ai_analyzed,
            "Rating": self.rating,
        }

    def to_template_context(self) -> dict[str, Any]:
        context = self.to_csv_row()

        def _safe(value: object) -> str:
            return " ".join(str(value or "").split())

        for key in (
            "Author",
            "Channel",
            "Title",
            "Summary",
            "Topic",
            "Tags",
            "Status",
            "Is Useful",
            "Is Transcribed",
            "Is AI Analyzed",
            "Rating",
        ):
            context[key] = _safe(context.get(key, ""))
        context["Transcript"] = self.transcript
        context["Author Wiki"] = f"[[{self.author}]]" if self.author else "[[]]"
        context["Channel Wiki"] = f"[[{self.channel}]]" if self.channel else "[[]]"
        context["Iframe Src"] = build_iframe_src(self.embed_url)
        return context


def build_watch_url(video_id: str) -> str:
    return f"https://www.facebook.com/watch/?v={video_id}"


def build_embed_url(video_id: str) -> str:
    return f"https://www.facebook.com/watch/?ref=saved&v={video_id}"


def build_iframe_src(embed_url: str) -> str:
    from urllib.parse import quote

    encoded = quote(embed_url, safe="")
    return (
        "https://www.facebook.com/plugins/video.php?"
        f"href={encoded}&width=500&show_text=false&height=889&appId"
    )

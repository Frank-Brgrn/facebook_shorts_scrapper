from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import frontmatter

from src.config import get_settings
from src.models import OBSIDIAN_FRONTMATTER_KEYS

FRONTMATTER_KEYS = list(OBSIDIAN_FRONTMATTER_KEYS)


def _clean_field_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return " ".join(value.split())


def _split_frontmatter(content: str) -> tuple[str, str] | None:
    if not content.startswith("---"):
        return None

    without_first = content[4:].lstrip("\n")
    end = without_first.find("\n---\n")
    if end == -1:
        return None

    block = without_first[:end]
    body = without_first[end + 5 :]
    return block, body


def _parse_frontmatter_block(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for index, key in enumerate(FRONTMATTER_KEYS):
        if index + 1 < len(FRONTMATTER_KEYS):
            next_key = FRONTMATTER_KEYS[index + 1]
            pattern = rf"^{re.escape(key)}:\s*(.*?)(?=^{re.escape(next_key)}:)"
        else:
            pattern = rf"^{re.escape(key)}:\s*(.*?)\Z"

        match = re.search(pattern, block, re.M | re.S)
        if match:
            fields[key] = _clean_field_value(match.group(1))
    return fields


def _render_frontmatter(metadata: dict[str, str]) -> str:
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        value = metadata.get(key, "")
        if value is None:
            value = ""
        lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _normalize_body(body: str) -> str:
    body = body.lstrip("\n")
    if body.startswith("---\n"):
        body = body[4:]
    return body


def _title_is_multiline(block: str) -> bool:
    match = re.search(r"^Title:\s*(.*?)(?=^URL:)", block, re.M | re.S)
    if not match:
        return False
    return "\n" in match.group(1)


def note_needs_repair(content: str) -> bool:
    split = _split_frontmatter(content)
    if split is None:
        return False

    block, body = split
    if _title_is_multiline(block):
        return True
    if body.startswith("---\n") or body.startswith("---\r\n"):
        return True

    try:
        frontmatter.loads(content)
    except Exception:
        return True
    return False


def repair_note_content(content: str) -> str | None:
    split = _split_frontmatter(content)
    if split is None:
        return None

    block, body = split
    metadata: dict[str, str]

    try:
        post = frontmatter.loads(content)
        metadata = {
            key: _clean_field_value(str(post.metadata.get(key, "") or ""))
            for key in FRONTMATTER_KEYS
        }
        for key, value in post.metadata.items():
            if key not in metadata and value not in (None, ""):
                metadata[key] = _clean_field_value(str(value))
    except Exception:
        metadata = _parse_frontmatter_block(block)

    if _title_is_multiline(block):
        metadata.update(_parse_frontmatter_block(block))

    for key in FRONTMATTER_KEYS:
        metadata.setdefault(key, "")

    repaired = f"{_render_frontmatter(metadata)}\n{_normalize_body(body)}"
    if repaired == content:
        return None
    return repaired


def repair_note(path: Path, *, dry_run: bool = False) -> bool:
    content = path.read_text(encoding="utf-8")
    if not note_needs_repair(content):
        return False

    repaired = repair_note_content(content)
    if repaired is None:
        return False

    if not dry_run:
        path.write_text(repaired, encoding="utf-8")
    return True


def repair_vault(vault_dir: Path, *, dry_run: bool = False) -> tuple[int, int]:
    repaired = 0
    scanned = 0
    for path in sorted(vault_dir.glob("*.md")):
        scanned += 1
        if repair_note(path, dry_run=dry_run):
            repaired += 1
    return scanned, repaired


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair Obsidian frontmatter broken by multi-line titles."
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Obsidian vault folder (defaults to OBSIDIAN_VAULT_DIR).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report files that would be repaired without writing changes.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    vault_dir = args.vault or settings.obsidian_vault_dir
    if not vault_dir.exists():
        print(f"Vault folder not found: {vault_dir}", file=sys.stderr)
        return 1

    scanned, repaired = repair_vault(vault_dir, dry_run=args.dry_run)
    action = "Would repair" if args.dry_run else "Repaired"
    print(f"{action} {repaired} of {scanned} note(s) in:")
    print(f"  {vault_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

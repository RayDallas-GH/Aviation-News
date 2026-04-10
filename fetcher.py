#!/usr/bin/env python3
"""RSS を取得し、キーワードで絞り込んで items.json を書き出す。"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "feeds.yaml"
OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))


@dataclass
class Item:
    title: str
    link: str
    published: str  # ISO8601 UTC
    summary: str
    source_id: str
    source_name: str


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def entry_published_iso(entry: Any) -> str:
    struct = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if struct:
        dt = datetime(*struct[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    return datetime.now(timezone.utc).isoformat()


def entry_summary(entry: Any) -> str:
    return (
        getattr(entry, "summary", None)
        or getattr(entry, "description", None)
        or ""
    )


def matches_keywords(haystack: str, keywords: list[str]) -> bool:
    if not haystack or not keywords:
        return False
    for kw in keywords:
        if not kw:
            continue
        if kw in haystack:
            return True
        if kw.isascii() and kw.lower() in haystack.lower():
            return True
    return False


def fetch_feed(url: str, source_id: str, source_name: str, keywords: list[str]) -> list[Item]:
    parsed = feedparser.parse(url)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        print(
            f"Warning: parse issue for {url}: {getattr(parsed, 'bozo_exception', '')}",
            file=sys.stderr,
        )
    out: list[Item] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        if not link:
            continue
        summary = entry_summary(entry)
        combined = f"{title}\n{summary}"
        if not matches_keywords(combined, keywords):
            continue
        out.append(
            Item(
                title=title.strip(),
                link=link.strip(),
                published=entry_published_iso(entry),
                summary=summary.strip(),
                source_id=source_id,
                source_name=source_name,
            )
        )
    return out


def dedupe_by_link(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    unique: list[Item] = []
    for it in items:
        if it.link in seen:
            continue
        seen.add(it.link)
        unique.append(it)
    return unique


def main() -> int:
    cfg = load_config()
    keywords: list[str] = list(cfg.get("keywords") or [])
    feeds = cfg.get("feeds") or []

    all_items: list[Item] = []
    for fd in feeds:
        url = fd.get("url")
        if not url:
            continue
        sid = fd.get("id", "unknown")
        sname = fd.get("name", sid)
        try:
            all_items.extend(fetch_feed(url, sid, sname, keywords))
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            return 1

    all_items = dedupe_by_link(all_items)
    all_items.sort(key=lambda x: x.published, reverse=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": [asdict(x) for x in all_items],
    }
    out_path = OUT_DIR / "items.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(all_items)} items to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

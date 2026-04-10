#!/usr/bin/env python3
"""RSS を取得し、キーワードで絞り込んで items.json を書き出す。"""

from __future__ import annotations

import html as html_module
import json
import os
import re
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
    groups: list[str]  # "jal" / "ana"（表示用の対比）


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_keyword_groups(cfg: dict[str, Any]) -> dict[str, list[str]]:
    g = cfg.get("keyword_groups")
    if isinstance(g, dict) and g:
        return {str(k): list(v) for k, v in g.items()}
    legacy = cfg.get("keywords") or []
    if legacy:
        return {"jal": list(legacy), "ana": list(legacy)}
    return {}


def union_keywords(keyword_groups: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for kws in keyword_groups.values():
        for kw in kws:
            if kw and kw not in seen:
                seen.add(kw)
                out.append(kw)
    return out


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


def strip_html(text: str) -> str:
    """RSS 要約に混ざる <input> 等のタグを除き、表示用の短文にする。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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


def classify_groups(
    haystack: str, keyword_groups: dict[str, list[str]]
) -> list[str]:
    out: list[str] = []
    for name, kws in sorted(keyword_groups.items()):
        if matches_keywords(haystack, kws):
            out.append(name)
    return out


def fetch_feed(
    url: str,
    source_id: str,
    source_name: str,
    keyword_groups: dict[str, list[str]],
    union_kws: list[str],
) -> list[Item]:
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
        summary_raw = entry_summary(entry)
        title_clean = strip_html(title)
        summary_clean = strip_html(summary_raw)
        combined = f"{title_clean}\n{summary_clean}"
        if not matches_keywords(combined, union_kws):
            continue
        groups = classify_groups(combined, keyword_groups)
        if not groups:
            continue
        out.append(
            Item(
                title=title_clean or title.strip(),
                link=link.strip(),
                published=entry_published_iso(entry),
                summary=summary_clean,
                source_id=source_id,
                source_name=source_name,
                groups=groups,
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
    keyword_groups = resolve_keyword_groups(cfg)
    if not keyword_groups:
        print("feeds.yaml に keyword_groups（または keywords）が必要です。", file=sys.stderr)
        return 1
    union_kws = union_keywords(keyword_groups)
    feeds = cfg.get("feeds") or []

    all_items: list[Item] = []
    for fd in feeds:
        url = fd.get("url")
        if not url:
            continue
        sid = fd.get("id", "unknown")
        sname = fd.get("name", sid)
        try:
            all_items.extend(
                fetch_feed(url, sid, sname, keyword_groups, union_kws)
            )
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

#!/usr/bin/env python3
"""industry_feeds.yaml に従い RSS を取得し、トラック別に industry_news.json を書き出す。"""

from __future__ import annotations

import html as html_module
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "industry_feeds.yaml"
OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))
OUT_PATH = OUT_DIR / "industry_news.json"

DISPLAY_ORDER = ["jp_oem", "intl_oem", "aam"]


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def matches_keywords(haystack: str, keywords: list[str]) -> bool:
    if not haystack or not keywords:
        return False
    for kw in keywords:
        k = str(kw).strip() if kw is not None else ""
        if not k:
            continue
        if k in haystack:
            return True
        if k.isascii() and k.lower() in haystack.lower():
            return True
    return False


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


def published_ts(iso_utc: str) -> float:
    try:
        s = iso_utc.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        print(f"Missing {CONFIG_PATH}", file=sys.stderr)
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def assign_track(
    combined: str,
    match_order: list[str],
    tracks_cfg: dict[str, Any],
) -> str | None:
    for tid in match_order:
        t = tracks_cfg.get(tid)
        if not isinstance(t, dict):
            continue
        inc = t.get("include") or []
        if isinstance(inc, list) and matches_keywords(combined, [str(x) for x in inc]):
            return tid
    return None


def main() -> int:
    cfg = load_config()
    feeds = cfg.get("feeds") or []
    if not feeds:
        print("industry_feeds.yaml に feeds がありません。", file=sys.stderr)
        return 1

    tracks_raw = cfg.get("tracks") or {}
    if not isinstance(tracks_raw, dict) or not tracks_raw:
        print("industry_feeds.yaml に tracks がありません。", file=sys.stderr)
        return 1

    tracks_cfg: dict[str, Any] = {str(k): v for k, v in tracks_raw.items() if isinstance(v, dict)}
    match_order = cfg.get("match_order") or ["aam", "intl_oem", "jp_oem"]
    if not isinstance(match_order, list):
        match_order = ["aam", "intl_oem", "jp_oem"]
    match_order = [str(x) for x in match_order if str(x) in tracks_cfg]

    exclude = cfg.get("exclude") or []
    if not isinstance(exclude, list):
        exclude = []

    buckets: dict[str, list[dict[str, Any]]] = {tid: [] for tid in tracks_cfg}
    seen_links: set[str] = set()

    for fd in feeds:
        url = fd.get("url")
        if not url:
            continue
        sid = str(fd.get("id", "unknown"))
        sname = str(fd.get("name", sid))
        parsed = feedparser.parse(url)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            print(
                f"Warning: parse issue for {url}: {getattr(parsed, 'bozo_exception', '')}",
                file=sys.stderr,
            )
        for entry in parsed.entries:
            title = getattr(entry, "title", "") or ""
            link = (getattr(entry, "link", "") or "").strip()
            if not link or link in seen_links:
                continue
            title_clean = strip_html(title) or title.strip()
            summary_clean = strip_html(entry_summary(entry))
            combined = f"{title_clean}\n{summary_clean}"

            if exclude and matches_keywords(combined, [str(x) for x in exclude if x]):
                continue

            tid = assign_track(combined, match_order, tracks_cfg)
            if not tid:
                continue

            seen_links.add(link)
            buckets[tid].append(
                {
                    "title": title_clean,
                    "link": link,
                    "published": entry_published_iso(entry),
                    "source_id": sid,
                    "source_name": sname,
                }
            )

    tracks_out: list[dict[str, Any]] = []
    for tid in DISPLAY_ORDER:
        if tid not in tracks_cfg:
            continue
        tcfg = tracks_cfg[tid]
        label = str(tcfg.get("label_ja") or tid)
        lim = int(tcfg.get("per_track_limit") or 8)
        items = buckets.get(tid) or []
        items.sort(key=lambda x: published_ts(x.get("published") or ""), reverse=True)
        tracks_out.append(
            {
                "id": tid,
                "label_ja": label,
                "items": items[:lim],
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "_readme": "industry_fetcher.py が生成。編集は industry_feeds.yaml。",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tracks": tracks_out,
    }
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n = sum(len(t["items"]) for t in tracks_out)
    print(f"Wrote {n} industry items in {len(tracks_out)} tracks to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

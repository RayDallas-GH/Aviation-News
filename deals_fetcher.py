#!/usr/bin/env python3
"""deals_sources.yaml の campaign_url を取得し、public/deals.json を自動生成する。"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("BeautifulSoup4 が必要です: pip install beautifulsoup4", file=sys.stderr)
    raise SystemExit(1)

CONFIG_PATH = Path(__file__).resolve().parent / "deals_sources.yaml"
OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))
OUT_PATH = OUT_DIR / "deals.json"
JST = timezone(timedelta(hours=9))

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def load_sources() -> list[dict[str, Any]]:
    if not CONFIG_PATH.is_file():
        print(f"Missing {CONFIG_PATH}", file=sys.stderr)
        return []
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    raw = data.get("sources")
    if not isinstance(raw, list):
        return []
    return [dict(x) for x in raw if isinstance(x, dict)]


def fetch_html(url: str, timeout: int = 45) -> str | None:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            return None
        req = Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.9"})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"Warning: fetch failed {url}: {e}", file=sys.stderr)
        return None


def extract_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        t = str(og["content"]).strip()
        if t:
            return t[:120]
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(" ", strip=True)
        if t:
            return t[:120]
    t_el = soup.find("title")
    if t_el and t_el.string:
        return str(t_el.string).strip()[:120]
    return ""


def extract_plain(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _context_window(text: str, start: int, end: int) -> str:
    return text[max(0, start - 220) : min(len(text), end + 40)]


def _boarding_heavy_window(win: str) -> bool:
    """搭乗期間など販売締切と紛らわしい文脈（販売系語が同じ窓に無い）。"""
    if re.search(r"搭乗期間|対象搭乗|ご搭乗", win) and not re.search(
        r"予約・販売|販売期間|販売開始|セール販売|期間限定SALE|予約[:：]",
        win,
    ):
        return True
    return False


def _date_in_year(year: int, mo: int, d: int) -> datetime | None:
    try:
        return datetime(year, mo, d, tzinfo=JST)
    except ValueError:
        return None


def _pick_best_end(candidates: list[tuple[int, int, int]], now_jst: datetime) -> str:
    """スコア最大の候補だけを使い、未来締切は最も近い日付を優先。"""
    if not candidates:
        return ""
    year = now_jst.year
    max_sc = max(c[2] for c in candidates)
    top = [(mo, d, sc) for mo, d, sc in candidates if sc == max_sc]
    today = now_jst.date()

    future: list[tuple[int, int]] = []
    past: list[tuple[int, int]] = []
    for mo, d, _ in top:
        dt = _date_in_year(year, mo, d)
        if not dt:
            continue
        if dt.date() >= today:
            future.append((mo, d))
        else:
            past.append((mo, d))

    if future:

        def ord_future(md: tuple[int, int]) -> int:
            dt = _date_in_year(year, md[0], md[1])
            return dt.date().toordinal() if dt else 10**9

        mo, d = min(future, key=ord_future)
        return f"{mo:02d}/{d:02d}"
    if past:

        def ord_past(md: tuple[int, int]) -> int:
            dt = _date_in_year(year, md[0], md[1])
            return dt.date().toordinal() if dt else 0

        mo, d = max(past, key=ord_past)
        return f"{mo:02d}/{d:02d}"
    return ""


def find_end_mmdd(text: str, now_jst: datetime) -> str:
    """本文から販売終了日っぽい 月/日 を MM/DD で返す（年なしは今年 JST）。"""
    candidates: list[tuple[int, int, int]] = []  # (month, day, score)

    for m in re.finditer(
        r"～\s*(\d{1,2})月(\d{1,2})日（[火水木金土日月]）\s*23:59",
        text,
    ):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            w = _context_window(text, m.start(), m.end())
            if _boarding_heavy_window(w):
                continue
            candidates.append((mo, d, 9))

    for m in re.finditer(
        r"(?:予約・販売期間|販売期間)\s*[：:][\s\S]{0,360}?～\s*(\d{1,2})月(\d{1,2})日",
        text,
    ):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            w = _context_window(text, m.start(), m.end())
            if _boarding_heavy_window(w):
                continue
            candidates.append((mo, d, 8))

    for m in re.finditer(
        r"(?:販売|予約|受付|キャンペーン|セール).*?(\d{1,2})月(\d{1,2})日\s*まで",
        text,
        flags=re.DOTALL,
    ):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            w = _context_window(text, m.start(), m.end())
            if _boarding_heavy_window(w):
                continue
            candidates.append((mo, d, 3))

    for m in re.finditer(r"(\d{1,2})月(\d{1,2})日\s*まで", text):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            w = _context_window(text, m.start(), m.end())
            if _boarding_heavy_window(w):
                continue
            candidates.append((mo, d, 2))

    for m in re.finditer(
        r"(\d{1,2})/(\d{1,2})（[火水木金土日月]）\s*\d{1,2}:\d{2}\s*まで",
        text,
    ):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            w = _context_window(text, m.start(), m.end())
            if _boarding_heavy_window(w):
                continue
            candidates.append((mo, d, 7))

    for m in re.finditer(r"～\s*(\d{1,2})/(\d{1,2})", text):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            w = _context_window(text, m.start(), m.end())
            if _boarding_heavy_window(w):
                continue
            candidates.append((mo, d, 4))

    return _pick_best_end(candidates, now_jst)


def decide_status(
    sale_name: str, end_mmdd: str, text: str, now_jst: datetime
) -> str:
    head = (sale_name + "\n" + text[:6000]).lower()
    if end_mmdd:
        mo, da = int(end_mmdd[:2]), int(end_mmdd[3:5])
        try:
            end_dt = datetime(now_jst.year, mo, da, 23, 59, 59, tzinfo=JST)
            if end_dt.date() < now_jst.date():
                return "none"
        except ValueError:
            return "none"
    if not sale_name or len(sale_name.strip()) < 3:
        return "none"
    if re.search(
        r"セール|キャンペーン|タイムセール|sale|プロモ|特価|割引|キャンペ|スペシャル|期間限定",
        head,
        re.I,
    ):
        return "active"
    if end_mmdd:
        return "active"
    return "none"


def fallback_row(src: dict[str, Any]) -> dict[str, Any]:
    return {
        "airline": str(src.get("airline") or ""),
        "airline_url": str(src.get("airline_url") or ""),
        "dot": str(src.get("dot") or "#888888"),
        "status": "none",
        "sale_name": "",
        "end_date": "",
    }


def merge_fallback_airlines(
    built: list[dict[str, Any]], fallback: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """取得失敗で空になった航空会社名をフォールバック JSON で補完。"""
    by_name = {str(x.get("airline")): x for x in built if x.get("airline")}
    for row in fallback:
        name = str(row.get("airline") or "")
        if name and name not in by_name:
            built.append(dict(row))
    return built


def row_from_source(src: dict[str, Any], now_jst: datetime) -> dict[str, Any]:
    base = {
        "airline": str(src.get("airline") or ""),
        "airline_url": str(src.get("airline_url") or ""),
        "dot": str(src.get("dot") or "#888888"),
    }
    url = str(src.get("campaign_url") or "").strip()
    if not url:
        out = fallback_row(src)
        return out

    html = fetch_html(url)
    if not html:
        return fallback_row(src)

    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(soup)
    plain = extract_plain(soup)
    end_mmdd = find_end_mmdd(plain, now_jst)
    sale_name = title
    if len(sale_name) > 80:
        sale_name = sale_name[:77] + "…"
    status = decide_status(sale_name, end_mmdd, plain, now_jst)
    out_sale = sale_name if len(sale_name.strip()) >= 3 else ""
    out_end = end_mmdd if end_mmdd else ""

    return {**base, "status": status, "sale_name": out_sale, "end_date": out_end}


def main() -> int:
    sources = load_sources()
    if not sources:
        print("deals_sources.yaml に sources がありません。", file=sys.stderr)
        return 1

    now_jst = datetime.now(timezone.utc).astimezone(JST)
    fetched_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    deals = [row_from_source(src, now_jst) for src in sources]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "_readme": "deals_fetcher.py が生成。編集は deals_sources.yaml かフォールバック deals.json。",
        "fetched_at": fetched_at_utc,
        "deals": deals,
    }
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(deals)} deals to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

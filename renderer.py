#!/usr/bin/env python3
"""items.json から閲覧用 index.html を生成する。AVIATION NEWS（3カラム＋お得情報＋メーカー・AAM）。"""

from __future__ import annotations

import html
import json
import os
import re

import yaml
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))
REPO_ROOT = Path(__file__).resolve().parent
ITEMS_PATH = OUT_DIR / "items.json"
DEALS_SRC = REPO_ROOT / "deals.json"
DEALS_OUT = OUT_DIR / "deals.json"
INDUSTRY_PATH = OUT_DIR / "industry_news.json"
FEEDS_YAML = REPO_ROOT / "feeds.yaml"
INDUSTRY_FEEDS_YAML = REPO_ROOT / "industry_feeds.yaml"
JST = timezone(timedelta(hours=9))

DEFAULT_INDUSTRY_TRACKS: list[dict[str, Any]] = [
    {"id": "jp_oem", "label_ja": "日系メーカー", "items": []},
    {"id": "intl_oem", "label_ja": "海外メーカー", "items": []},
    {"id": "aam", "label_ja": "空飛ぶクルマ", "items": []},
]

# 那覇お得情報見出し「那覇発着 … お得情報」の間。絵文字の例: "🛫" 飛行機 / "🏝️" 島 / "✈️"
DEALS_SECTION_MARK = "\U0001f3dd\U0000fe0f"  # 🏝️ 島

CAT_LABELS: dict[str, str] = {
    "route": "路線",
    "finance": "財務",
    "fleet": "機材",
    "intl": "国際線",
    "general": "その他",
}


def parse_iso_utc(iso_utc: str) -> datetime | None:
    if not iso_utc:
        return None
    try:
        s = iso_utc.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST)
    except Exception:
        return None


def format_header_jst(iso_utc: str) -> str:
    dt = parse_iso_utc(iso_utc)
    if not dt:
        return iso_utc
    return dt.strftime("%Y/%m/%d %H:%M JST")


def format_item_time(published_iso: str) -> str:
    dt = parse_iso_utc(published_iso)
    if not dt:
        return ""
    now = datetime.now(timezone.utc).astimezone(JST)
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.date() == (now.date() - timedelta(days=1)):
        return "昨日"
    return dt.strftime("%m/%d")


def published_ts(iso_utc: str) -> float:
    dt = parse_iso_utc(iso_utc)
    if not dt:
        return 0.0
    return dt.timestamp()


def sort_for_column(items: list[dict]) -> list[dict]:
    """BREAKING を先頭に固定し、同一ブロック内は新しい順。安定のため link でタイブレーク。"""

    def key(it: dict) -> tuple[int, float, str]:
        brk = 0 if it.get("breaking") else 1
        ts = -published_ts(it.get("published") or "")
        link = it.get("link") or ""
        return (brk, ts, link)

    return sorted(items, key=key)


def items_for_group(items: list[dict], group: str) -> list[dict]:
    return [it for it in items if group in (it.get("groups") or [])]


def count_with_group(items: list[dict], group: str) -> int:
    return sum(1 for it in items if group in (it.get("groups") or []))


def load_industry_tracks() -> tuple[list[dict[str, Any]], str, bool]:
    """(tracks, generated_at 表示用 JST 行, ファイルが存在したか)。"""
    if not INDUSTRY_PATH.is_file():
        return ([], "", False)
    try:
        data = json.loads(INDUSTRY_PATH.read_text(encoding="utf-8"))
        raw = data.get("tracks")
        if not isinstance(raw, list):
            return ([], "", True)
        gen = data.get("generated_at") or ""
        gen_line = format_header_jst(str(gen)) if gen else ""
        return (list(raw), gen_line, True)
    except Exception:
        return ([], "", True)


def render_industry_row(it: dict[str, Any]) -> str:
    title = html.escape(str(it.get("title") or ""))
    link_raw = str(it.get("link") or "").strip()
    link_esc = escape_attr(link_raw)
    t = format_item_time(str(it.get("published") or ""))
    time_html = (
        f'<span class="industry-row__time mono">{html.escape(t)}</span>' if t else ""
    )
    return f"""<div class="industry-row">
  <div class="industry-row__head">{time_html}<a class="industry-row__title" href="{link_esc}" target="_blank" rel="noopener noreferrer">{title}</a></div>
</div>"""


def render_industry_section(tracks: list[dict[str, Any]]) -> str:
    accent_classes = ["col-accent-jp", "col-accent-intl", "col-accent-aam"]
    blocks: list[str] = []
    for i, tr in enumerate(tracks):
        if not isinstance(tr, dict):
            continue
        tid = str(tr.get("id") or f"t{i}")
        label = html.escape(str(tr.get("label_ja") or tid))
        items = tr.get("items") if isinstance(tr.get("items"), list) else []
        accent = accent_classes[i] if i < len(accent_classes) else "col-accent-intl"
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "-", tid)
        if items:
            body = "\n".join(
                render_industry_row(it) for it in items if isinstance(it, dict)
            )
        else:
            body = '<p class="industry-empty muted">該当記事はありません</p>'
        n = len([x for x in items if isinstance(x, dict)])
        blocks.append(
            f"""<article class="col {accent}" aria-labelledby="h-ind-{safe_id}">
  <header class="col-banner">
    <h2 id="h-ind-{safe_id}" class="col-title">{label}</h2>
    <span class="col-count mono">{n}</span>
  </header>
  <div class="col-body industry-col-body">{body}</div>
</article>"""
        )
    return "\n".join(blocks)


def load_deals_with_meta() -> tuple[list[dict[str, Any]], str | None]:
    """deals_fetcher が書いた OUT_DIR/deals.json を優先。戻り値は (deals, fetched_at ISO または None)。"""
    for path in (DEALS_OUT, DEALS_SRC):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("deals")
            if not isinstance(raw, list):
                continue
            fa = data.get("fetched_at")
            fetched = str(fa).strip() if fa else None
            return (list(raw), fetched or None)
        except Exception:
            continue
    return ([], None)


def escape_attr(val: str) -> str:
    return html.escape(val, quote=True)


def _rss_feed_entries_from_yaml(path: Path) -> list[tuple[str, str]]:
    """YAML の feeds から (表示名, URL) を取り出す。URL 空は名前のみ。"""
    out: list[tuple[str, str]] = []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return out
    for fd in raw.get("feeds") or []:
        if not isinstance(fd, dict):
            continue
        name = str(fd.get("name") or fd.get("id") or "").strip()
        url = str(fd.get("url") or "").strip()
        if not name:
            continue
        if url.startswith(("http://", "https://")):
            out.append((name, url))
        else:
            out.append((name, ""))
    return out


def _format_feed_link_entries(entries: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    for name, url in entries:
        if url:
            parts.append(
                f'<a href="{escape_attr(url)}" target="_blank" rel="noopener noreferrer">'
                f"{html.escape(name)}</a>"
            )
        else:
            parts.append(html.escape(name))
    return "、".join(parts) if parts else ""


def _merge_feed_entries_unique(paths: Iterable[Path]) -> list[tuple[str, str]]:
    """複数 YAML の feeds を順に読み、同一 URL（または名前のみの行）は1回だけ残す。"""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for path in paths:
        for name, url in _rss_feed_entries_from_yaml(path):
            key = url.strip().rstrip("/").lower() if url else f"name:{name.lower()}"
            if key in seen:
                continue
            seen.add(key)
            out.append((name, url))
    return out


def build_sources_footer_html() -> str:
    """ページ最下部用の引用・データ元（小さめの HTML 断片）。"""
    merged = _merge_feed_entries_unique((FEEDS_YAML, INDUSTRY_FEEDS_YAML))
    src_body = _format_feed_link_entries(merged)
    if not src_body:
        aw = "https://www.aviationwire.jp/feed/"
        src_body = (
            f'<a href="{escape_attr(aw)}" target="_blank" rel="noopener noreferrer">'
            "Aviation Wire</a>"
        )
    future_note = html.escape("今後は Flight Global などを追加予定です。")
    deals_note = html.escape("各航空会社の公式キャンペーンページ（上表のセール列リンク）。")
    return f"""<div class="sources-foot" role="note" aria-label="引用・データ元">
  <p class="sources-foot__line"><span class="sources-foot__label">引用元サイト</span>{src_body}</p>
  <p class="sources-foot__line sources-foot__future muted">{future_note}</p>
  <p class="sources-foot__line"><span class="sources-foot__label">お得情報</span>{deals_note}</p>
</div>"""


def badge_breaking() -> str:
    return '<span class="badge badge--breaking">BREAKING</span>'


def badge_category(cat: str) -> str:
    label = html.escape(CAT_LABELS.get(cat, cat))
    safe = re.sub(r"[^a-z0-9_-]", "", str(cat).lower())
    if not safe:
        safe = "misc"
    return f'<span class="badge badge--cat-{safe}">{label}</span>'


def company_badge_html(column: str, it: dict) -> str:
    """列に応じた社名バッジ。旧 items.json の airline_badge は oth のみフォールバック。"""
    col = column if column in ("jal", "ana", "oth") else "oth"
    key = f"badge_{col}"
    txt = it.get(key) or ""
    if not txt and col == "oth":
        txt = it.get("airline_badge") or ""
    if not txt:
        return ""
    return f'<span class="badge badge--company-{col}">{html.escape(str(txt))}</span>'


def render_news_row(it: dict, *, column: str) -> str:
    title = html.escape(it.get("title") or "(無題)")
    raw_link = it.get("link") or "#"
    link_esc = html.escape(raw_link, quote=True)
    tline = format_item_time(it.get("published") or "")
    cats = it.get("categories") or []
    if not isinstance(cats, list):
        cats = []
    cat_str = " ".join(str(c) for c in cats if c)
    brk = bool(it.get("breaking"))
    badges: list[str] = []
    if brk:
        badges.append(badge_breaking())
    for c in cats:
        badges.append(badge_category(str(c)))
    cb = company_badge_html(column, it)
    if cb:
        badges.append(cb)
    badges_html = "".join(badges) if badges else ""
    row_cls = "news-row"
    if brk:
        row_cls += " news-row--breaking"
    time_cls = "news-row__time mono"
    data_cats = escape_attr(cat_str)
    data_brk = "1" if brk else "0"
    return f"""<article class="{row_cls}" data-categories="{data_cats}" data-breaking="{data_brk}">
  <div class="news-row__top">
    <div class="news-row__badges">{badges_html}</div>
    <span class="{time_cls}">{html.escape(tline)}</span>
  </div>
  <h3 class="news-row__title"><a href="{link_esc}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
</article>"""


def render_column(
    col_id: str,
    title: str,
    subtitle: str,
    accent_class: str,
    items: list[dict],
) -> str:
    n = len(items)
    count_html = f'<span class="col-count mono">{n}</span>'
    if items:
        body = "\n".join(render_news_row(it, column=col_id) for it in items)
    else:
        body = '<p class="col-empty">該当なし</p>'
    return f"""<section class="col {accent_class}" aria-labelledby="h-{col_id}">
  <header class="col-banner">
    <h2 id="h-{col_id}" class="col-title">{title}</h2>
    {count_html}
  </header>
  <p class="col-sub mono">{html.escape(subtitle)}</p>
  <div class="col-body">{body}</div>
</section>"""


def render_deals_rows(deals: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for d in deals:
        airline_name = str(d.get("airline") or "")
        airline_esc = html.escape(airline_name)
        url_raw = str(d.get("airline_url") or "").strip()
        if url_raw.startswith(("https://", "http://")):
            url_esc = html.escape(url_raw, quote=True)
            airline_cell = (
                f'<a class="deal-airline-link" href="{url_esc}" '
                f'target="_blank" rel="noopener noreferrer">{airline_esc}</a>'
            )
        else:
            airline_cell = airline_esc
        sale_u = str(d.get("campaign_url") or "").strip()
        abbr = str(d.get("sale_abbr") or "").strip()
        sale_link_label = html.escape(f"{abbr}セール" if abbr else "セール")
        if sale_u.startswith(("https://", "http://")):
            su_esc = html.escape(sale_u, quote=True)
            sale_cell = (
                f'<a class="deal-sale-url" href="{su_esc}" '
                f'target="_blank" rel="noopener noreferrer">{sale_link_label}</a>'
            )
        else:
            sale_cell = '<span class="muted">—</span>'
        dot = html.escape(str(d.get("dot") or "#888"))
        st = str(d.get("status") or "none")
        if st == "active":
            status_html = '<span class="deal-badge deal-badge--on">開催中</span>'
        else:
            status_html = '<span class="deal-badge deal-badge--off">なし</span>'
        end = d.get("end_date") or ""
        end_html = (
            f'<span class="mono">〜 {html.escape(str(end))}</span>'
            if end
            else '<span class="mono muted">—</span>'
        )
        rows.append(
            f"""<tr>
  <td class="deal-airline"><span class="deal-dot" style="background:{dot}"></span>{airline_cell}</td>
  <td class="deal-sale-page">{sale_cell}</td>
  <td class="deal-status">{status_html}</td>
  <td class="deal-end">{end_html}</td>
</tr>"""
        )
    if not rows:
        rows.append(
            '<tr><td colspan="4" class="deal-empty">deals_fetcher.py で生成するか、deals.json に行を追加してください。</td></tr>'
        )
    return "\n".join(rows)


def main() -> int:
    if not ITEMS_PATH.is_file():
        print(f"Missing {ITEMS_PATH}; run fetcher.py first.", file=sys.stderr)
        return 1

    data = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    items: list[dict] = data.get("items") or []
    generated = data.get("generated_at", "")
    gen_line = format_header_jst(generated) if generated else ""

    total = len(items)
    jal_n = count_with_group(items, "jal")
    ana_n = count_with_group(items, "ana")
    oth_n = count_with_group(items, "oth")

    jal_items = sort_for_column(items_for_group(items, "jal"))
    ana_items = sort_for_column(items_for_group(items, "ana"))
    oth_items = sort_for_column(items_for_group(items, "oth"))

    col_jal = render_column(
        "jal",
        "JALグループ",
        "JAL / JTA / JAC / J-AIR / RAC / ZIPAIR / ジェットスタージャパン",
        "col-accent-jal",
        jal_items,
    )
    col_ana = render_column(
        "ana",
        "ANAグループ",
        "ANA / ANAウィングス / Peach / AIRDO / ソラシド / スターフライヤー",
        "col-accent-ana",
        ana_items,
    )
    col_oth = render_column(
        "oth",
        "独立系・LCC",
        "スカイマーク / FDA / IBEX / スプリングジャパン / 天草 / ORC / トキエア",
        "col-accent-oth",
        oth_items,
    )

    deals, deals_fetched_iso = load_deals_with_meta()
    deals_body = render_deals_rows(deals)
    deals_asof_line = (
        format_header_jst(deals_fetched_iso)
        if deals_fetched_iso
        else (gen_line or "—")
    )
    deals_asof_caption = (
        "各社公式ページを自動取得した時刻（JST）"
        if deals_fetched_iso
        else "ビルド時刻に準じます（deals_fetcher 未実行または deals.json のみ）"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not DEALS_OUT.is_file() and DEALS_SRC.is_file():
        shutil.copy2(DEALS_SRC, DEALS_OUT)

    empty_main = ""
    if not items:
        empty_main = '<p class="page-empty">該当する記事はありませんでした（feeds.yaml のキーワードを調整してください）。</p>'

    deals_heading_mark = (
        f'<span class="section-label__mark" aria-hidden="true">'
        f"{html.escape(DEALS_SECTION_MARK)}"
        f"</span>"
    )

    industry_tracks, industry_gen_line, industry_file_ok = load_industry_tracks()
    if not industry_tracks:
        industry_tracks = [
            {"id": x["id"], "label_ja": x["label_ja"], "items": list(x["items"])}
            for x in DEFAULT_INDUSTRY_TRACKS
        ]
    industry_cols = render_industry_section(industry_tracks)
    if industry_gen_line:
        industry_meta = f'<p class="industry-meta muted mono">取得: {html.escape(industry_gen_line)}</p>'
    elif not industry_file_ok:
        industry_meta = (
            '<p class="industry-meta muted">'
            "industry_fetcher.py を実行すると記事が表示されます。"
            "</p>"
        )
    else:
        industry_meta = ""

    sources_footer = build_sources_footer_html()

    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Cache-Control" content="max-age=0, must-revalidate" />
  <meta http-equiv="refresh" content="300" />
  <title>AVIATION NEWS</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --color-bg: #e9f3fc;
      --color-bg-mid: #f0f7fd;
      --color-surface: rgba(255, 255, 255, 0.92);
      --color-text: #0f2744;
      --color-muted: #5a6f85;
      --color-border: #c5d9eb;
      --link-accent: #0b6cb5;
      --sky-deep: #0a3d62;
      --jal-accent: #E24B4A;
      --jal-bg: #fff5f5;
      --jal-text: #7a2222;
      --ana-accent: #1e7cc8;
      --ana-bg: #e3f1fc;
      --ana-text: #0a4a7a;
      --oth-accent: #c47a12;
      --oth-bg: #fdf6ea;
      --oth-text: #5c3d0c;
      --badge-breaking-bg: #E24B4A;
      --badge-breaking-fg: #ffffff;
      --badge-route-bg: #E6F1FB;
      --badge-route-fg: #0C447C;
      --badge-finance-bg: #EAF3DE;
      --badge-finance-fg: #27500A;
      --badge-fleet-bg: #EEEDFE;
      --badge-fleet-fg: #3C3489;
      --badge-intl-bg: #FCEBEB;
      --badge-intl-fg: #791F1F;
      --badge-general-bg: #e8eef5;
      --badge-general-fg: #3d4f63;
      --badge-airline-bg: #fdf0e0;
      --badge-airline-fg: #5c3d0c;
      --deal-on-bg: #EAF3DE;
      --deal-on-fg: #27500A;
      --deal-off-bg: #e8eef5;
      --deal-off-fg: #6b7c8f;
      --font-sans: "Inter", "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, system-ui, sans-serif;
      --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --color-bg: #0c1929;
        --color-bg-mid: #0f2135;
        --color-surface: rgba(18, 36, 56, 0.94);
        --color-text: #e8f1fa;
        --color-muted: #8aa3b8;
        --color-border: #2a4a6a;
        --link-accent: #5eb0f0;
        --sky-deep: #b8d9f5;
        --jal-bg: #2c1818;
        --jal-text: #f5c8c8;
        --ana-bg: #152a40;
        --ana-text: #b8daf5;
        --oth-bg: #2a2318;
        --oth-text: #edd9b8;
        --badge-route-bg: #153048;
        --badge-route-fg: #b8d4f0;
        --badge-finance-bg: #1a2e22;
        --badge-finance-fg: #c5e0a8;
        --badge-fleet-bg: #222640;
        --badge-fleet-fg: #cfc8ff;
        --badge-intl-bg: #2a1818;
        --badge-intl-fg: #f0c0c0;
        --badge-general-bg: #1e2d3d;
        --badge-general-fg: #c5d0dc;
        --badge-airline-bg: #2a2318;
        --badge-airline-fg: #edd9b8;
        --deal-on-bg: #1a2e22;
        --deal-on-fg: #c5e0a8;
        --deal-off-bg: #1e2d3d;
        --deal-off-fg: #8aa3b8;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html {{
      font-size: 16px;
    }}
    body {{
      margin: 0;
      font-family: var(--font-sans);
      font-size: 16px;
      line-height: 1.55;
      color: var(--color-text);
      background-color: var(--color-bg);
      background-image: linear-gradient(
        168deg,
        #d4e9fb 0%,
        var(--color-bg) 32%,
        var(--color-bg-mid) 58%,
        #f7fbff 100%
      );
      background-attachment: fixed;
      min-height: 100vh;
    }}
    @media (prefers-color-scheme: dark) {{
      body {{
        background-image: linear-gradient(
          168deg,
          #071018 0%,
          var(--color-bg) 40%,
          var(--color-bg-mid) 70%,
          #122a42 100%
        );
      }}
    }}
    .mono {{ font-family: var(--font-mono); font-weight: 500; }}
    a {{ color: inherit; }}
    .page {{
      max-width: 72rem;
      margin: 0 auto;
      padding: 1rem 1rem 2.5rem;
    }}
    .site-header {{
      border-bottom: 1px solid var(--color-border);
      padding-bottom: 0.85rem;
      margin-bottom: 1rem;
      background: linear-gradient(
        to bottom,
        rgba(255, 255, 255, 0.55),
        transparent
      );
      border-radius: 0 0 12px 12px;
    }}
    @media (prefers-color-scheme: dark) {{
      .site-header {{
        background: linear-gradient(
          to bottom,
          rgba(30, 60, 90, 0.35),
          transparent
        );
      }}
    }}
    .brand {{
      font-family: var(--font-mono);
      font-weight: 500;
      font-size: 1.875rem;
      letter-spacing: 0.04em;
      margin: 0 0 0.35rem 0;
    }}
    .brand-avi {{ color: var(--link-accent); }}
    .brand-news {{ color: var(--sky-deep); }}
    .header-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      align-items: center;
      color: var(--color-muted);
      font-family: var(--font-mono);
      font-weight: 500;
      font-size: 0.875rem;
    }}
    .header-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem 0.75rem;
      margin-top: 0.5rem;
      font-family: var(--font-mono);
      font-weight: 500;
      font-size: 0.875rem;
    }}
    .stat {{
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 6px;
      padding: 0.2rem 0.45rem;
    }}
    .stat-total {{ color: var(--color-text); }}
    .stat-jal {{ color: var(--jal-accent); }}
    .stat-ana {{ color: var(--ana-accent); }}
    .stat-oth {{ color: var(--oth-accent); }}
    .header-filter {{
      margin-top: 0.55rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.8125rem;
      font-family: var(--font-mono);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--color-muted);
    }}
    .header-filter select {{
      font: inherit;
      font-size: 0.875rem;
      padding: 0.3rem 0.45rem;
      border-radius: 4px;
      border: 1px solid var(--color-border);
      background: var(--color-surface);
      color: var(--color-text);
    }}
    .section-label {{
      font-family: var(--font-mono);
      font-weight: 500;
      font-size: 24px;
      letter-spacing: 0.04em;
      text-transform: none;
      color: var(--color-muted);
      margin: 0 0 0.5rem 0;
      line-height: 1.25;
    }}
    .section-label__mark {{
      display: inline-block;
      margin: 0 0.12em;
      line-height: 1;
      vertical-align: -0.06em;
      font-size: 0.92em;
      font-family: "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif;
      color: var(--link-accent);
    }}
    .grid-news {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.75rem;
      align-items: start;
    }}
    @media (max-width: 900px) {{
      .grid-news {{ grid-template-columns: 1fr; }}
    }}
    .col {{
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      overflow: hidden;
      min-height: 6rem;
      box-shadow: 0 4px 20px rgba(11, 80, 140, 0.07);
    }}
    @media (prefers-color-scheme: dark) {{
      .col {{
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.35);
      }}
    }}
    .col-accent-jal {{ border-top: 2px solid var(--jal-accent); }}
    .col-accent-ana {{ border-top: 2px solid var(--ana-accent); }}
    .col-accent-oth {{ border-top: 2px solid var(--oth-accent); }}
    .col-banner {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.55rem 0.65rem 0.15rem;
      font-weight: 500;
    }}
    .col-accent-jal .col-banner {{ background: var(--jal-bg); }}
    .col-accent-ana .col-banner {{ background: var(--ana-bg); }}
    .col-accent-oth .col-banner {{ background: var(--oth-bg); }}
    .col-title {{
      margin: 0;
      font-size: 1.125rem;
      font-weight: 500;
    }}
    .col-accent-jal .col-title {{ color: var(--jal-text); }}
    .col-accent-ana .col-title {{ color: var(--ana-text); }}
    .col-accent-oth .col-title {{ color: var(--oth-text); }}
    .col-count {{ font-size: 0.875rem; color: var(--color-muted); }}
    .col-sub {{
      margin: 0;
      padding: 0 0.65rem 0.35rem;
      font-size: 0.8125rem;
      color: var(--color-muted);
    }}
    .col-body {{ padding: 0 0.5rem 0.35rem; }}
    .news-row {{
      padding: 0.45rem 0.35rem;
      border-bottom: 1px solid var(--color-border);
    }}
    .news-row:last-child {{ border-bottom: none; }}
    .news-row:hover {{ background: rgba(11, 108, 181, 0.06); }}
    @media (prefers-color-scheme: dark) {{
      .news-row:hover {{ background: rgba(94, 176, 240, 0.08); }}
    }}
    .news-row--breaking {{
      background: rgba(226, 75, 74, 0.08);
    }}
    .news-row__top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.35rem;
    }}
    .news-row__badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.2rem;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 500;
      padding: 0.12rem 0.35rem;
      border-radius: 3px;
      line-height: 1.2;
      font-family: var(--font-sans);
    }}
    .badge--breaking {{
      background: var(--badge-breaking-bg);
      color: var(--badge-breaking-fg);
    }}
    .badge--cat-route {{ background: var(--badge-route-bg); color: var(--badge-route-fg); }}
    .badge--cat-finance {{ background: var(--badge-finance-bg); color: var(--badge-finance-fg); }}
    .badge--cat-fleet {{ background: var(--badge-fleet-bg); color: var(--badge-fleet-fg); }}
    .badge--cat-intl {{ background: var(--badge-intl-bg); color: var(--badge-intl-fg); }}
    .badge--cat-general {{ background: var(--badge-general-bg); color: var(--badge-general-fg); }}
    .badge--cat-misc {{ background: var(--badge-general-bg); color: var(--badge-general-fg); }}
    .badge--airline {{ background: var(--badge-airline-bg); color: var(--badge-airline-fg); }}
    .badge--company-jal {{
      background: var(--jal-bg);
      color: var(--jal-text);
    }}
    .badge--company-ana {{
      background: var(--ana-bg);
      color: var(--ana-text);
    }}
    .badge--company-oth {{
      background: var(--badge-airline-bg);
      color: var(--badge-airline-fg);
    }}
    .news-row__time {{
      flex: 0 0 auto;
      font-size: 0.875rem;
      color: var(--color-muted);
    }}
    .news-row__title {{
      margin: 0.25rem 0 0 0;
      font-size: 1rem;
      font-weight: 400;
    }}
    .news-row--breaking .news-row__title {{ font-size: 1.0625rem; font-weight: 500; }}
    .news-row__title a {{
      color: var(--link-accent);
      text-decoration: none;
    }}
    .news-row__title a:hover {{ text-decoration: underline; }}
    .col-empty, .page-empty {{
      color: var(--color-muted);
      padding: 0.5rem 0.35rem;
      margin: 0;
      font-size: 1rem;
    }}
    .page-empty {{ text-align: center; padding: 1.5rem 0.5rem; }}
    .deals-wrap {{ margin-top: 1.75rem; }}
    .deals-table {{
      width: 100%;
      table-layout: fixed;
      border-collapse: collapse;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(11, 80, 140, 0.07);
    }}
    @media (prefers-color-scheme: dark) {{
      .deals-table {{
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.35);
      }}
    }}
    .deals-table th, .deals-table td {{
      padding: 0.3rem 0.35rem;
      border-bottom: 1px solid var(--color-border);
      text-align: left;
      vertical-align: middle;
    }}
    .deals-table tr:last-child td {{ border-bottom: none; }}
    .deals-table th {{
      font-family: var(--font-mono);
      font-size: 0.8125rem;
      font-weight: 500;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--color-muted);
      background: var(--color-bg);
    }}
    .deals-table td {{
      font-size: 0.9375rem;
    }}
    .deal-airline {{
      width: 22%;
      min-width: 0;
      font-weight: 500;
    }}
    .deal-airline-link {{
      color: var(--link-accent);
      text-decoration: none;
    }}
    .deal-airline-link:hover {{
      text-decoration: underline;
      filter: brightness(0.92);
    }}
    @media (prefers-color-scheme: dark) {{
      .deal-airline-link:hover {{
        filter: brightness(1.12);
      }}
    }}
    .deal-dot {{
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 0.35rem;
      vertical-align: middle;
    }}
    .deal-sale-page {{
      width: 4.5rem;
      text-align: center;
      white-space: nowrap;
    }}
    .deal-sale-url {{
      font-size: 0.8125rem;
      font-weight: 500;
      color: var(--link-accent);
      text-decoration: none;
    }}
    .deal-sale-url:hover {{ text-decoration: underline; filter: brightness(0.92); }}
    @media (prefers-color-scheme: dark) {{
      .deal-sale-url:hover {{ filter: brightness(1.12); }}
    }}
    .deal-status {{ width: 4.5rem; text-align: center; white-space: nowrap; }}
    .deal-end {{ width: 5.5rem; font-size: 0.875rem; text-align: right; white-space: nowrap; }}
    .deal-badge {{
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 500;
      padding: 0.16rem 0.4rem;
      border-radius: 4px;
      font-family: var(--font-sans);
    }}
    .deal-badge--on {{ background: var(--deal-on-bg); color: var(--deal-on-fg); }}
    .deal-badge--off {{ background: var(--deal-off-bg); color: var(--deal-off-fg); }}
    .deal-empty {{ text-align: center; color: var(--color-muted); }}
    .deals-meta {{
      margin: 0.5rem 0 0;
      font-size: 0.8125rem;
      line-height: 1.45;
    }}
    .industry-wrap {{ margin-top: 1.75rem; }}
    .industry-meta {{
      margin: 0 0 0.35rem 0;
      font-size: 0.8125rem;
      line-height: 1.45;
    }}
    .grid-industry {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.75rem;
      align-items: start;
    }}
    @media (max-width: 900px) {{
      .grid-industry {{ grid-template-columns: 1fr; }}
    }}
    .col-accent-jp {{ border-top: 2px solid #2e7d32; }}
    .col-accent-jp .col-banner {{ background: rgba(46, 125, 50, 0.1); }}
    .col-accent-jp .col-title {{ color: #1b5e20; }}
    .col-accent-intl {{ border-top: 2px solid var(--ana-accent); }}
    .col-accent-intl .col-banner {{ background: var(--ana-bg); }}
    .col-accent-intl .col-title {{ color: var(--ana-text); }}
    .col-accent-aam {{ border-top: 2px solid var(--oth-accent); }}
    .col-accent-aam .col-banner {{ background: var(--oth-bg); }}
    .col-accent-aam .col-title {{ color: var(--oth-text); }}
    @media (prefers-color-scheme: dark) {{
      .col-accent-jp .col-banner {{ background: rgba(46, 125, 50, 0.18); }}
      .col-accent-jp .col-title {{ color: #c8e6c9; }}
    }}
    .industry-col-body {{ padding-bottom: 0.5rem; }}
    .industry-row {{
      padding: 0.38rem 0.35rem;
      border-bottom: 1px solid var(--color-border);
    }}
    .industry-row:last-child {{ border-bottom: none; }}
    .industry-row:hover {{ background: rgba(11, 108, 181, 0.06); }}
    @media (prefers-color-scheme: dark) {{
      .industry-row:hover {{ background: rgba(94, 176, 240, 0.08); }}
    }}
    .industry-row__head {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 0.35rem 0.5rem;
    }}
    .industry-row__time {{
      flex: 0 0 auto;
      font-size: 0.8125rem;
      color: var(--color-muted);
    }}
    .industry-row__title {{
      flex: 1 1 12rem;
      font-size: 0.9375rem;
      font-weight: 400;
      color: var(--link-accent);
      text-decoration: none;
    }}
    .industry-row__title:hover {{ text-decoration: underline; }}
    .industry-empty {{
      margin: 0.35rem 0.35rem 0.5rem;
      font-size: 0.875rem;
    }}
    .muted {{ color: var(--color-muted); }}
    footer {{
      margin-top: 2rem;
      font-size: 0.8125rem;
      color: var(--color-muted);
      text-align: center;
      font-family: var(--font-mono);
    }}
    .footer-lead {{
      margin: 0 auto;
      max-width: 42rem;
    }}
    .sources-foot {{
      margin-top: 1rem;
      padding-top: 1rem;
      border-top: 1px solid var(--color-border);
      font-size: 0.6875rem;
      line-height: 1.55;
      color: var(--color-muted);
      text-align: left;
      max-width: 42rem;
      margin-left: auto;
      margin-right: auto;
      font-family: var(--font-sans);
    }}
    .sources-foot a {{
      color: var(--link-accent);
      text-decoration: underline;
      text-underline-offset: 2px;
    }}
    @media (prefers-color-scheme: dark) {{
      .sources-foot a {{ color: #7eb8ea; }}
    }}
    .sources-foot__line {{
      margin: 0.22rem 0;
    }}
    .sources-foot__line:first-child {{ margin-top: 0; }}
    .sources-foot__line:last-child {{ margin-bottom: 0; }}
    .sources-foot__label {{
      display: inline-block;
      margin-right: 0.4rem;
      font-weight: 500;
      font-family: var(--font-mono);
      color: var(--color-muted);
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="site-header">
      <h1 class="brand"><span class="brand-avi">AVIATION</span><span class="brand-news"> NEWS</span></h1>
      <div class="header-meta">
        <span>最終更新 {html.escape(gen_line)} | 自動更新 5分</span>
      </div>
      <div class="header-stats" aria-label="記事数サマリー">
        <span class="stat stat-total">総記事 <strong>{total}</strong></span>
        <span class="stat stat-jal">JAL関連 <strong>{jal_n}</strong></span>
        <span class="stat stat-ana">ANA関連 <strong>{ana_n}</strong></span>
        <span class="stat stat-oth">独立系・LCC <strong>{oth_n}</strong></span>
      </div>
      <div class="header-filter">
        <label for="cat-filter">カテゴリ</label>
        <select id="cat-filter" aria-label="カテゴリでニュースを絞り込み">
          <option value="all">全カテゴリ</option>
          <option value="route">路線</option>
          <option value="finance">財務</option>
          <option value="fleet">機材</option>
          <option value="intl">国際線</option>
        </select>
      </div>
    </header>
    <main>
      {empty_main}
      <p class="section-label">Airline news</p>
      <div class="grid-news" role="region" aria-label="エアラインニュース三カラム">
        {col_jal}
        {col_ana}
        {col_oth}
      </div>
      <section class="deals-wrap" aria-labelledby="h-deals">
        <p class="section-label" id="h-deals">那覇発着 {deals_heading_mark} お得情報</p>
        <table class="deals-table">
          <thead>
            <tr>
              <th>エアライン</th>
              <th>セール</th>
              <th>ステータス</th>
              <th>終了日</th>
            </tr>
          </thead>
          <tbody>
            {deals_body}
          </tbody>
        </table>
        <p class="deals-meta muted" aria-live="polite">お得情報の反映: <span class="mono">{html.escape(deals_asof_line)}</span> — {html.escape(deals_asof_caption)}</p>
      </section>
      <section class="industry-wrap" aria-labelledby="h-industry">
        <p class="section-label" id="h-industry">メーカー・モビリティ</p>
        {industry_meta}
        <div class="grid-industry" role="region" aria-label="メーカーおよび空飛ぶクルマ関連ニュース">
          {industry_cols}
        </div>
      </section>
    </main>
    <footer>
      <p class="footer-lead">自動生成ダッシュボード。記事の著作権は各リンク先に帰属します。</p>
      {sources_footer}
    </footer>
  </div>
  <script>
    (function () {{
      var sel = document.getElementById("cat-filter");
      if (!sel) return;
      function apply() {{
        var v = sel.value;
        var nodes = document.querySelectorAll(".news-row");
        nodes.forEach(function (n) {{
          if (v === "all") {{
            n.style.display = "";
            return;
          }}
          var cats = (n.getAttribute("data-categories") || "").trim().split(/\\s+/).filter(Boolean);
          n.style.display = cats.indexOf(v) >= 0 ? "" : "none";
        }});
      }}
      sel.addEventListener("change", apply);
    }})();
  </script>
</body>
</html>
"""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    index_path = OUT_DIR / "index.html"
    index_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

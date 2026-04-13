#!/usr/bin/env python3
"""items.json から閲覧用 index.html を生成する。AVIATION NEWS ダッシュボード仕様（3カラム＋那覇お得情報）。"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))
REPO_ROOT = Path(__file__).resolve().parent
ITEMS_PATH = OUT_DIR / "items.json"
DEALS_SRC = REPO_ROOT / "deals.json"
JST = timezone(timedelta(hours=9))

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


def load_deals() -> list[dict[str, Any]]:
    if not DEALS_SRC.is_file():
        return []
    try:
        data = json.loads(DEALS_SRC.read_text(encoding="utf-8"))
        raw = data.get("deals")
        return list(raw) if isinstance(raw, list) else []
    except Exception:
        return []


def escape_attr(val: str) -> str:
    return html.escape(val, quote=True)


def badge_breaking() -> str:
    return '<span class="badge badge--breaking">BREAKING</span>'


def badge_category(cat: str) -> str:
    label = html.escape(CAT_LABELS.get(cat, cat))
    safe = re.sub(r"[^a-z0-9_-]", "", str(cat).lower())
    if not safe:
        safe = "misc"
    return f'<span class="badge badge--cat-{safe}">{label}</span>'


def badge_airline(name: str) -> str:
    if not name:
        return ""
    return f'<span class="badge badge--airline">{html.escape(name)}</span>'


def render_news_row(it: dict, *, show_airline_badge: bool) -> str:
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
    ab = it.get("airline_badge") or ""
    if show_airline_badge and ab:
        badges.append(badge_airline(str(ab)))
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
    *,
    show_airline_badge: bool,
) -> str:
    n = len(items)
    count_html = f'<span class="col-count mono">{n}</span>'
    if items:
        body = "\n".join(
            render_news_row(it, show_airline_badge=show_airline_badge) for it in items
        )
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
        airline = html.escape(str(d.get("airline") or ""))
        dot = html.escape(str(d.get("dot") or "#888"))
        st = str(d.get("status") or "none")
        if st == "active":
            status_html = '<span class="deal-badge deal-badge--on">開催中</span>'
        else:
            status_html = '<span class="deal-badge deal-badge--off">なし</span>'
        sale = d.get("sale_name") or ""
        if sale:
            sale_html = f'<span class="deal-sale">{html.escape(str(sale))}</span>'
        else:
            sale_html = '<span class="deal-sale deal-sale--muted">現在セール設定なし</span>'
        route = html.escape(str(d.get("route") or "—"))
        end = d.get("end_date") or ""
        end_html = (
            f'<span class="mono">〜 {html.escape(str(end))}</span>'
            if end
            else '<span class="mono muted">—</span>'
        )
        rows.append(
            f"""<tr>
  <td class="deal-airline"><span class="deal-dot" style="background:{dot}"></span>{airline}</td>
  <td class="deal-status">{status_html}</td>
  <td class="deal-name">{sale_html}</td>
  <td class="deal-route mono">{route}</td>
  <td class="deal-end">{end_html}</td>
</tr>"""
        )
    if not rows:
        rows.append(
            '<tr><td colspan="5" class="deal-empty">deals.json に行を追加すると表示されます。</td></tr>'
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
        show_airline_badge=False,
    )
    col_ana = render_column(
        "ana",
        "ANAグループ",
        "ANA / ANAウィングス / Peach / Air Japan / AIRDO / ソラシド / スターフライヤー",
        "col-accent-ana",
        ana_items,
        show_airline_badge=False,
    )
    col_oth = render_column(
        "oth",
        "独立系・LCC",
        "スカイマーク / FDA / IBEX / スプリングジャパン / 天草 / ORC",
        "col-accent-oth",
        oth_items,
        show_airline_badge=True,
    )

    deals = load_deals()
    deals_body = render_deals_rows(deals)

    if DEALS_SRC.is_file():
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEALS_SRC, OUT_DIR / "deals.json")

    empty_main = ""
    if not items:
        empty_main = '<p class="page-empty">該当する記事はありませんでした（feeds.yaml のキーワードを調整してください）。</p>'

    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="300" />
  <title>AVIATION NEWS</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --color-bg: #f4f4f1;
      --color-surface: #ffffff;
      --color-text: #1a1a1a;
      --color-muted: #5c5c58;
      --color-border: #e3e0d8;
      --jal-accent: #E24B4A;
      --jal-bg: #FCEBEB;
      --jal-text: #791F1F;
      --ana-accent: #378ADD;
      --ana-bg: #E6F1FB;
      --ana-text: #0C447C;
      --oth-accent: #BA7517;
      --oth-bg: #FAEEDA;
      --oth-text: #633806;
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
      --badge-general-bg: #F1EFE8;
      --badge-general-fg: #444441;
      --badge-airline-bg: #FAEEDA;
      --badge-airline-fg: #633806;
      --deal-on-bg: #EAF3DE;
      --deal-on-fg: #27500A;
      --deal-off-bg: #F1EFE8;
      --deal-off-fg: #888780;
      --font-sans: "Inter", "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, system-ui, sans-serif;
      --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --color-bg: #121210;
        --color-surface: #1a1a17;
        --color-text: #eceae4;
        --color-muted: #a8a69e;
        --color-border: #2e2e29;
        --jal-bg: #2a1a1a;
        --jal-text: #f0c8c8;
        --ana-bg: #152535;
        --ana-text: #c8dcf5;
        --oth-bg: #2a2215;
        --oth-text: #edd9b8;
        --badge-route-bg: #1a2a38;
        --badge-route-fg: #b8d4f0;
        --badge-finance-bg: #1f2a18;
        --badge-finance-fg: #c5e0a8;
        --badge-fleet-bg: #222130;
        --badge-fleet-fg: #cfc8ff;
        --badge-intl-bg: #2a1818;
        --badge-intl-fg: #f0c0c0;
        --badge-general-bg: #242320;
        --badge-general-fg: #d6d4cc;
        --badge-airline-bg: #2a2215;
        --badge-airline-fg: #edd9b8;
        --deal-on-bg: #1f2a18;
        --deal-on-fg: #c5e0a8;
        --deal-off-bg: #242320;
        --deal-off-fg: #888780;
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
      background: var(--color-bg);
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
    }}
    .brand {{
      font-family: var(--font-mono);
      font-weight: 500;
      font-size: 1.875rem;
      letter-spacing: 0.04em;
      margin: 0 0 0.35rem 0;
    }}
    .brand-avi {{ color: var(--color-text); }}
    .brand-news {{ color: var(--jal-accent); }}
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
      border-radius: 8px;
      overflow: hidden;
      min-height: 6rem;
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
    .news-row:hover {{ background: rgba(0,0,0,0.03); }}
    @media (prefers-color-scheme: dark) {{
      .news-row:hover {{ background: rgba(255,255,255,0.04); }}
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
      color: var(--ana-accent);
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
      border-collapse: collapse;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 8px;
      overflow: hidden;
    }}
    .deals-table th, .deals-table td {{
      padding: 0.45rem 0.5rem;
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
      font-size: 1rem;
    }}
    .deal-airline {{
      width: 148px;
      font-weight: 500;
    }}
    .deal-dot {{
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 0.35rem;
      vertical-align: middle;
    }}
    .deal-status {{ width: 96px; }}
    .deal-name {{ width: auto; }}
    .deal-route {{ width: 160px; font-size: 1rem; }}
    .deal-end {{ width: 112px; font-size: 1rem; }}
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
    .deal-sale--muted {{ color: var(--color-muted); }}
    .deal-empty {{ text-align: center; color: var(--color-muted); }}
    .muted {{ color: var(--color-muted); }}
    footer {{
      margin-top: 2rem;
      font-size: 0.8125rem;
      color: var(--color-muted);
      text-align: center;
      font-family: var(--font-mono);
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
        <p class="section-label" id="h-deals">那覇発着 · お得情報</p>
        <table class="deals-table">
          <thead>
            <tr>
              <th>エアライン</th>
              <th>ステータス</th>
              <th>セール名</th>
              <th>路線</th>
              <th>終了日</th>
            </tr>
          </thead>
          <tbody>
            {deals_body}
          </tbody>
        </table>
      </section>
    </main>
    <footer>
      自動生成ダッシュボード。記事の著作権は各リンク先に帰属します。
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

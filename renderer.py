#!/usr/bin/env python3
"""items.json から閲覧用 index.html を生成する。JAL / ANA を2カラムで対比表示。"""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))
ITEMS_PATH = OUT_DIR / "items.json"
JST = timezone(timedelta(hours=9))


def format_jst(iso_utc: str) -> str:
    try:
        s = iso_utc.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    except Exception:
        return iso_utc


def render_article(it: dict) -> str:
    title = html.escape(it.get("title") or "(無題)")
    raw_link = it.get("link") or "#"
    link_esc = html.escape(raw_link, quote=True)
    pub = format_jst(it.get("published") or "")
    src = html.escape(it.get("source_name") or it.get("source_id") or "")
    summ = it.get("summary") or ""
    if summ:
        summ = html.escape(summ[:400]) + ("…" if len(summ) > 400 else "")
    summ_block = f'<p class="summary">{summ}</p>' if summ else ""
    return f"""<article class="item">
  <h3 class="title"><a href="{link_esc}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
  <p class="meta"><span class="date">{html.escape(pub)}</span> · <span class="src">{src}</span></p>
  {summ_block}
</article>"""


def sort_by_published(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: x.get("published") or "", reverse=True)


def split_by_groups(items: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """両社 / JALのみ / ANAのみ に分類（link 単位）。"""
    both: list[dict] = []
    jal_only: list[dict] = []
    ana_only: list[dict] = []
    for it in items:
        g = it.get("groups") or []
        has_j = "jal" in g
        has_a = "ana" in g
        if has_j and has_a:
            both.append(it)
        elif has_j:
            jal_only.append(it)
        elif has_a:
            ana_only.append(it)
        else:
            both.append(it)
    return (
        sort_by_published(both),
        sort_by_published(jal_only),
        sort_by_published(ana_only),
    )


def main() -> int:
    if not ITEMS_PATH.is_file():
        print(f"Missing {ITEMS_PATH}; run fetcher.py first.", file=sys.stderr)
        return 1

    data = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    items = data.get("items") or []
    generated = data.get("generated_at", "")
    gen_line = format_jst(generated) if generated else ""

    both, jal_only, ana_only = split_by_groups(items)

    section_both = ""
    if both:
        blocks = "\n".join(render_article(it) for it in both)
        section_both = f"""
  <section class="section section-both" aria-labelledby="h-both">
    <h2 id="h-both" class="section-title">両社・グループに関連</h2>
    <p class="section-note">タイトル・要約に JAL 系と ANA 系の両方が含まれる記事</p>
    <div class="section-body">{blocks}</div>
  </section>"""

    blocks_j = "\n".join(render_article(it) for it in jal_only) if jal_only else '<p class="empty">該当なし</p>'
    blocks_a = "\n".join(render_article(it) for it in ana_only) if ana_only else '<p class="empty">該当なし</p>'

    if not items:
        empty_all = '<p class="empty page-empty">該当する記事はありませんでした（feeds.yaml のキーワードを調整してください）。</p>'
        grid_inner = f'<div class="compare">{empty_all}</div>'
    else:
        grid_inner = f"""
  <div class="compare" role="region" aria-label="JAL と ANA の対比">
    <section class="col col-jal" aria-labelledby="h-jal">
      <h2 id="h-jal" class="col-head">JAL・グループ</h2>
      <p class="col-sub">日本航空 / ZIPAIR など</p>
      <div class="col-body">{blocks_j}</div>
    </section>
    <section class="col col-ana" aria-labelledby="h-ana">
      <h2 id="h-ana" class="col-head">ANA・グループ</h2>
      <p class="col-sub">全日空 / ANA HD など</p>
      <div class="col-body">{blocks_a}</div>
    </section>
  </div>"""

    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>JAL / ANA 関連ニュース（Aviation Wire）</title>
  <style>
    :root {{
      --jal: #c40018;
      --jal-bg: #fff5f5;
      --ana: #003894;
      --ana-bg: #f3f7fc;
      --border: #e0e0e0;
      font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, system-ui, sans-serif;
      line-height: 1.55;
      color: #1a1a1a;
    }}
    body {{ max-width: 60rem; margin: 0 auto; padding: 1.25rem 1rem 2rem; background: #fafafa; }}
    header {{ margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 2px solid var(--border); }}
    h1 {{ font-size: 1.4rem; margin: 0 0 0.35rem 0; letter-spacing: 0.02em; }}
    .generated {{ color: #555; font-size: 0.88rem; margin: 0; }}
    .section-both {{ margin-bottom: 1.75rem; background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.1rem; }}
    .section-title {{ font-size: 1.05rem; margin: 0 0 0.25rem 0; }}
    .section-note {{ font-size: 0.82rem; color: #666; margin: 0 0 1rem 0; }}
    .compare {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      align-items: start;
    }}
    @media (max-width: 720px) {{
      .compare {{ grid-template-columns: 1fr; }}
    }}
    .col {{
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--border);
      min-height: 8rem;
    }}
    .col-jal {{ background: var(--jal-bg); border-top: 4px solid var(--jal); }}
    .col-ana {{ background: var(--ana-bg); border-top: 4px solid var(--ana); }}
    .col-head {{
      font-size: 1.1rem;
      margin: 0;
      padding: 0.85rem 1rem 0.15rem;
      color: #111;
    }}
    .col-jal .col-head {{ color: var(--jal); }}
    .col-ana .col-head {{ color: var(--ana); }}
    .col-sub {{ font-size: 0.78rem; color: #555; margin: 0 0 0.5rem; padding: 0 1rem; }}
    .col-body {{ padding: 0.5rem 1rem 1rem; }}
    .item {{ margin-bottom: 1.35rem; }}
    .item:last-child {{ margin-bottom: 0; }}
    .title {{ font-size: 0.98rem; margin: 0 0 0.3rem 0; font-weight: 600; }}
    .title a {{ color: #0b57d0; text-decoration: none; }}
    .title a:hover {{ text-decoration: underline; }}
    .meta {{ font-size: 0.8rem; color: #555; margin: 0 0 0.4rem 0; }}
    .summary {{ font-size: 0.88rem; color: #444; margin: 0.35rem 0 0 0; }}
    .empty {{ color: #777; font-size: 0.9rem; margin: 0.5rem 0; }}
    .page-empty {{ text-align: center; padding: 2rem 1rem; }}
    footer {{ margin-top: 2.5rem; font-size: 0.78rem; color: #888; text-align: center; }}
  </style>
</head>
<body>
  <header>
    <h1>JAL / ANA 関連ニュース</h1>
    <p class="generated">データソース: Aviation Wire（RSS）· 生成: {html.escape(gen_line)}</p>
  </header>
  <main>
{section_both}
{grid_inner}
  </main>
  <footer>
    自動生成レポート。記事本文の著作権は各リンク先に帰属します。
  </footer>
</body>
</html>
"""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_path = OUT_DIR / "index.html"
    index_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

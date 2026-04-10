#!/usr/bin/env python3
"""items.json から閲覧用 index.html を生成する。"""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DIR = Path(os.environ.get("OUT_DIR", "public"))
ITEMS_PATH = OUT_DIR / "items.json"
# UTC+9（zoneinfo/tzdata に依存しない — CI でも安定）
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


def main() -> int:
    if not ITEMS_PATH.is_file():
        print(f"Missing {ITEMS_PATH}; run fetcher.py first.", file=sys.stderr)
        return 1

    data = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    items = data.get("items") or []
    generated = data.get("generated_at", "")

    rows: list[str] = []
    for it in items:
        title = html.escape(it.get("title") or "(無題)")
        raw_link = it.get("link") or "#"
        link_esc = html.escape(raw_link, quote=True)
        pub = format_jst(it.get("published") or "")
        src = html.escape(it.get("source_name") or it.get("source_id") or "")
        summ = it.get("summary") or ""
        if summ:
            summ = html.escape(summ[:400]) + ("…" if len(summ) > 400 else "")
        summ_block = f'<p class="summary">{summ}</p>' if summ else ""
        rows.append(
            f"""<article class="item">
  <h2 class="title"><a href="{link_esc}" target="_blank" rel="noopener noreferrer">{title}</a></h2>
  <p class="meta"><span class="date">{html.escape(pub)}</span> · <span class="src">{src}</span></p>
  {summ_block}
</article>"""
        )

    body = (
        "\n".join(rows)
        if rows
        else '<p class="empty">該当する記事はありませんでした（キーワードを調整してください）。</p>'
    )

    gen_line = format_jst(generated) if generated else ""

    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>JAL / ANA 関連ニュース（Aviation Wire）</title>
  <style>
    :root {{ font-family: system-ui, sans-serif; line-height: 1.5; color: #1a1a1a; }}
    body {{ max-width: 52rem; margin: 0 auto; padding: 1.5rem; }}
    header {{ margin-bottom: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 1rem; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 0.5rem 0; }}
    .generated {{ color: #666; font-size: 0.9rem; margin: 0; }}
    .item {{ margin-bottom: 1.75rem; }}
    .title {{ font-size: 1.1rem; margin: 0 0 0.35rem 0; }}
    .title a {{ color: #0b57d0; text-decoration: none; }}
    .title a:hover {{ text-decoration: underline; }}
    .meta {{ font-size: 0.85rem; color: #555; margin: 0 0 0.5rem 0; }}
    .summary {{ font-size: 0.95rem; color: #444; margin: 0.5rem 0 0 0; }}
    .empty {{ color: #666; }}
    footer {{ margin-top: 3rem; font-size: 0.8rem; color: #888; }}
  </style>
</head>
<body>
  <header>
    <h1>JAL / ANA 関連ニュース</h1>
    <p class="generated">データソース: Aviation Wire（RSS）· キーワードでフィルタ · 生成: {html.escape(gen_line)}</p>
  </header>
  <main>
{body}
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

#!/usr/bin/env python3
"""前回スナップショットと比較し、新規記事リンクがあればメール通知（CI 用・テスト向け）。"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any

STATE_NAME = "notify_state.json"


def load_dotenv_file(path: Path) -> None:
    """リポジトリルートの .env を読み、未設定の環境変数だけ埋める（値はログに出さない）。"""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        os.environ[key] = val


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def collect_article_links_and_titles(out_dir: Path) -> tuple[list[str], dict[str, str]]:
    """items.json と industry_news.json から (リンク順序保持リスト, url->title)。"""
    ordered: list[str] = []
    titles: dict[str, str] = {}

    items_path = out_dir / "items.json"
    raw = _read_json(items_path)
    if isinstance(raw, dict):
        for it in raw.get("items") or []:
            if not isinstance(it, dict):
                continue
            link = str(it.get("link") or "").strip()
            if not link or link in titles:
                continue
            titles[link] = str(it.get("title") or "(無題)")
            ordered.append(link)

    ind_path = out_dir / "industry_news.json"
    raw = _read_json(ind_path)
    if isinstance(raw, dict):
        for tr in raw.get("tracks") or []:
            if not isinstance(tr, dict):
                continue
            for it in tr.get("items") or []:
                if not isinstance(it, dict):
                    continue
                link = str(it.get("link") or "").strip()
                if not link or link in titles:
                    continue
                titles[link] = str(it.get("title") or "(無題)")
                ordered.append(link)

    return ordered, titles


def send_resend(api_key: str, from_addr: str, to_addr: str, subject: str, body: str) -> None:
    payload = json.dumps(
        {
            "from": from_addr,
            "to": [to_addr],
            "subject": subject,
            "text": body,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def send_smtp(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=60) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg)


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    load_dotenv_file(repo_root / ".env")

    if os.environ.get("NOTIFY_EMAIL_DISABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        print("notify_email: disabled by NOTIFY_EMAIL_DISABLED", file=sys.stderr)
        return 0

    out_dir = Path(os.environ.get("OUT_DIR", "public"))
    state_path = Path(os.environ.get("NOTIFY_STATE_PATH", STATE_NAME))

    ordered, title_by_link = collect_article_links_and_titles(out_dir)
    current_set = set(ordered)

    state = _read_json(state_path)
    if not isinstance(state, dict) or "links" not in state:
        state_path.write_text(
            json.dumps({"links": sorted(current_set)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            "notify_email: baseline snapshot saved (no email on first run)",
            file=sys.stderr,
        )
        return 0

    prev_set = set(state.get("links") or [])
    new_links = [u for u in ordered if u not in prev_set]

    def save_snapshot() -> None:
        state_path.write_text(
            json.dumps({"links": sorted(current_set)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if not new_links:
        save_snapshot()
        print("notify_email: no new links", file=sys.stderr)
        return 0

    to_addr = (os.environ.get("NOTIFY_EMAIL_TO") or "").strip()
    if not to_addr:
        save_snapshot()
        print(
            "notify_email: NOTIFY_EMAIL_TO unset; skipping send (state updated)",
            file=sys.stderr,
        )
        return 0

    lines = [f"新着 {len(new_links)} 件（Aviation-News / RSS 由来）", ""]
    for url in new_links:
        lines.append(title_by_link.get(url, url))
        lines.append(url)
        lines.append("")

    body = "\n".join(lines).strip() + "\n"
    subject = f"[Aviation-News] 新着 {len(new_links)} 件"

    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()

    if not resend_key and not smtp_host:
        save_snapshot()
        print(
            "notify_email: RESEND_API_KEY or SMTP_HOST unset; state updated, no send",
            file=sys.stderr,
        )
        return 0

    try:
        if resend_key:
            from_addr = (os.environ.get("NOTIFY_EMAIL_FROM") or "").strip()
            if not from_addr:
                print(
                    "notify_email: NOTIFY_EMAIL_FROM required for Resend",
                    file=sys.stderr,
                )
                return 1
            send_resend(resend_key, from_addr, to_addr, subject, body)
            print("notify_email: sent via Resend", file=sys.stderr)
        else:
            port = int(os.environ.get("SMTP_PORT") or "587")
            user = (os.environ.get("SMTP_USER") or "").strip()
            password = (os.environ.get("SMTP_PASSWORD") or "").strip()
            from_addr = (os.environ.get("NOTIFY_EMAIL_FROM") or user).strip()
            if not user or not password:
                print(
                    "notify_email: SMTP_USER / SMTP_PASSWORD required",
                    file=sys.stderr,
                )
                return 1
            send_smtp(
                smtp_host, port, user, password, from_addr, to_addr, subject, body
            )
            print("notify_email: sent via SMTP", file=sys.stderr)
    except urllib.error.HTTPError as e:
        err_body = e.read() if hasattr(e, "read") else b""
        print(f"notify_email: HTTP error {e.code}: {err_body!r}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"notify_email: send failed: {e}", file=sys.stderr)
        return 1

    save_snapshot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
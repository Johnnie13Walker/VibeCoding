#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path


DEFAULT_CHANNEL = "PobedaAirlines"
POST_RE = re.compile(r'data-post="([^"]+)/(\d+)"')
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

KEYWORD_RE = re.compile(
    r"(промокод|промо\s*код|promo\s*code|promocode|купон)",
    re.IGNORECASE,
)
CODE_RE = re.compile(r"\b([A-Z0-9]{5,14})\b")
PROMO_CAPTURE_RE = re.compile(
    r"(?:промокод|промо\s*код|promo\s*code|promocode)\s*[:\-—]?\s*([A-Z0-9А-Я]{4,14})",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Telegram channel for promo codes")
    parser.add_argument("--channel", default=os.getenv("PROMO_CHANNEL", DEFAULT_CHANNEL))
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to state json. Default: <project>/logs/pobeda_promocode_state.json",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        default=True,
        help="On first run store latest post id and do not alert",
    )
    parser.add_argument(
        "--no-bootstrap",
        dest="bootstrap",
        action="store_false",
        help="On first run process current posts immediately",
    )
    parser.add_argument("--timeout", type=int, default=20)
    return parser.parse_args()


def script_paths() -> tuple[Path, Path]:
    base_dir = Path(__file__).resolve().parents[1]
    notify_script = base_dir / "scripts" / "notify_telegram.sh"
    return base_dir, notify_script


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_channel_html(channel: str, timeout: int) -> str:
    url = f"https://t.me/s/{channel}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_posts(page_html: str, channel: str) -> list[dict]:
    matches = list(POST_RE.finditer(page_html))
    posts: list[dict] = []
    for idx, m in enumerate(matches):
        channel_name, post_id_str = m.group(1), m.group(2)
        if channel_name.lower() != channel.lower():
            continue

        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(page_html)
        chunk = page_html[start:end]

        text_match = re.search(
            r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>',
            chunk,
            flags=re.DOTALL,
        )
        raw_text = text_match.group(1) if text_match else ""
        clean_text = html.unescape(TAG_RE.sub(" ", raw_text))
        clean_text = SPACE_RE.sub(" ", clean_text).strip()

        post_id = int(post_id_str)
        posts.append(
            {
                "id": post_id,
                "text": clean_text,
                "url": f"https://t.me/{channel}/{post_id}",
            }
        )

    posts.sort(key=lambda p: p["id"])
    return posts


def find_promocode(text: str) -> tuple[bool, str]:
    if not text:
        return False, ""

    if not KEYWORD_RE.search(text):
        return False, ""

    m = PROMO_CAPTURE_RE.search(text)
    if m:
        code = m.group(1).upper()
        if any("A" <= ch <= "Z" for ch in code):
            return True, code

    tokens = [t for t in CODE_RE.findall(text.upper()) if not t.startswith("HTTP")]
    if tokens:
        for token in tokens:
            if any("A" <= ch <= "Z" for ch in token):
                return True, token

    return False, ""


def send_alert(notify_script: Path, channel: str, post: dict, code: str) -> None:
    snippet = post["text"][:350]
    if code:
        message = (
            f"Найден промокод в @{channel}\n"
            f"Код: {code}\n"
            f"Пост: {post['url']}\n"
            f"Текст: {snippet}"
        )
    else:
        message = (
            f"Возможно промокод в @{channel}\n"
            f"Пост: {post['url']}\n"
            f"Текст: {snippet}"
        )

    subprocess.run(["bash", str(notify_script), message], check=False)


def main() -> int:
    args = parse_args()
    base_dir, notify_script = script_paths()

    state_file = Path(args.state_file) if args.state_file else (base_dir / "logs" / "pobeda_promocode_state.json")
    state = load_state(state_file)
    last_seen_id = int(state.get("last_seen_id", 0))

    try:
        page_html = fetch_channel_html(args.channel, args.timeout)
    except Exception as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 1

    posts = extract_posts(page_html, args.channel)
    if not posts:
        print("No posts parsed")
        return 1

    latest_id = posts[-1]["id"]

    if last_seen_id == 0 and args.bootstrap:
        save_state(state_file, {"last_seen_id": latest_id})
        print(f"Bootstrap complete at post {latest_id}")
        return 0

    new_posts = [p for p in posts if p["id"] > last_seen_id]
    alerts_sent = 0

    for post in new_posts:
        is_promo, code = find_promocode(post["text"])
        if is_promo:
            send_alert(notify_script, args.channel, post, code)
            alerts_sent += 1

    save_state(state_file, {"last_seen_id": latest_id})
    print(f"Checked {len(new_posts)} new posts, alerts sent: {alerts_sent}, latest_id: {latest_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

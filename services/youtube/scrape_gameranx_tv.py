from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_DIR / "docs" / "data" / "youtube"
OUTPUT_PATH = DATA_DIR / "gameranx_tv.json"
CACHE_PATH = DATA_DIR / "channel_cache.json"

CHANNEL_NAME = "gameranx"
CHANNEL_URL = "https://www.youtube.com/@gameranxTV"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_channel_id_via_ytdlp(channel_url: str, timeout: int) -> str:
    command = ["python", "-m", "yt_dlp", "--flat-playlist", "--dump-single-json", "--playlist-end", "1", channel_url]
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True,
        timeout=max(30, timeout * 10),
    )
    payload = json.loads(completed.stdout)
    channel_id = str(payload.get("channel_id", "")).strip() or str(payload.get("id", "")).strip()
    if not channel_id:
        raise ValueError(f"yt-dlp could not resolve channel id from {channel_url}")
    return channel_id


def resolve_channel_id_via_html(channel_url: str, timeout: int) -> str:
    request = urllib.request.Request(
        channel_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; my-dashboard-youtube/1.0)", "Accept": "text/html,*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    for pattern in [
        r'"channelId"\s*:\s*"([^"]+)"',
        r'<meta\s+itemprop="channelId"\s+content="([^"]+)"',
        r'"externalId"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    raise ValueError(f"Could not resolve channel id from {channel_url}")


def get_channel_id(timeout: int) -> str:
    cache = load_cache()
    cached_id = str(cache.get(CHANNEL_URL, {}).get("channel_id", "")).strip()
    if cached_id:
        print(f"Using cached channel id: {cached_id}", flush=True)
        return cached_id
    print(f"Resolving channel id for {CHANNEL_NAME}...", flush=True)
    try:
        channel_id = resolve_channel_id_via_ytdlp(CHANNEL_URL, timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, ValueError):
        channel_id = resolve_channel_id_via_html(CHANNEL_URL, timeout)
    cache[CHANNEL_URL] = {
        "channel_id": channel_id,
        "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    save_cache(cache)
    return channel_id


def atom_text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path, ATOM_NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def fetch_rss_items(channel_id: str, limit: int, timeout: int) -> list[dict]:
    feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + urllib.parse.quote(channel_id, safe="")
    request = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; my-dashboard-youtube/1.0)", "Accept": "application/xml,*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        xml_text = resp.read().decode("utf-8", errors="replace")
    root = ET.fromstring(xml_text)
    items: list[dict] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        video_id = atom_text(entry, "yt:videoId")
        title = atom_text(entry, "atom:title")
        published_at = atom_text(entry, "atom:published")
        updated_at = atom_text(entry, "atom:updated")
        link = ""
        entry_link = entry.find("atom:link[@rel='alternate']", ATOM_NS)
        if entry_link is not None:
            link = (entry_link.attrib.get("href") or "").strip()
        if not link and video_id:
            link = f"https://www.youtube.com/watch?v={video_id}"
        items.append({
            "id": f"yt-{video_id}" if video_id else "",
            "video_id": video_id,
            "title": title,
            "url": link,
            "published_at": published_at,
            "updated_at": updated_at,
            "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else "",
        })
        if limit > 0 and len(items) >= limit:
            break
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Scrape latest uploads from {CHANNEL_NAME} via RSS.")
    parser.add_argument("--limit", type=int, default=15, help="Max videos to fetch (default: 15).")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds (default: 20).")
    args = parser.parse_args()

    timeout = max(5, args.timeout)

    try:
        channel_id = get_channel_id(timeout)
        print(f"Fetching RSS feed for {CHANNEL_NAME}...", flush=True)
        items = fetch_rss_items(channel_id, limit=max(1, args.limit), timeout=timeout)
        payload = {
            "source": "youtube-rss",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "channel_name": CHANNEL_NAME,
            "channel_id": channel_id,
            "channel_url": CHANNEL_URL,
            "items_count": len(items),
            "items": items,
        }
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {payload['items_count']} item(s) to {OUTPUT_PATH}", flush=True)
    except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Error scraping {CHANNEL_NAME}: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

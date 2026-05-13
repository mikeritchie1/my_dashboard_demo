from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get
from event_tags import tag_event, is_excluded_event
from sync_docs import sync_events_data_to_docs


BASE_URL = env_get("SCRAPE_QUICKET_EVENTS_URL_TEMPLATE", "https://www.quicket.co.za/events/{page}/")
# 0 means no hard limit: scrape all matching events in the configured window.
EVENTS_MAX_ITEMS = int(env_get("SCRAPE_QUICKET_MAX_ITEMS", "0"))
REPO_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_DIR / "docs" / "data" / "events"
JSON_OUTPUT = OUTPUT_DIR / "quicket_events.json"
LOCAL_TZ = timezone(timedelta(hours=2), "SAST")


def fetch_page(page: int) -> str:
    url = BASE_URL.format(page="" if page == 1 else f"{page}/")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; my-dashboard/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_events(page_html: str) -> list[dict]:
    matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    events: list[dict] = []
    for match in matches:
        payload = html.unescape(match).strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            data = [data]
        events.extend(item for item in data if item.get("@type") == "Event")
    return events


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LOCAL_TZ)


def location_text(event: dict) -> str:
    location = event.get("location") or {}
    address = location.get("address") or {}
    bits = [
        location.get("name", ""),
        address.get("streetAddress", ""),
        address.get("addressLocality", ""),
        address.get("addressRegion", ""),
    ]
    return " ".join(str(bit) for bit in bits if bit)


def is_cape_town_event(event: dict) -> bool:
    text = f"{event.get('name', '')} {location_text(event)}".lower()
    return "cape town" in text


def event_summary(event: dict) -> dict:
    start = parse_dt(event.get("startDate"))
    end = parse_dt(event.get("endDate")) or start
    location = event.get("location") or {}
    address = location.get("address") or {}
    image = event.get("image") or []
    offers = event.get("offers") or []
    offer = offers[0] if offers else {}
    title = event.get("name", "").strip()
    venue = str(location.get("name", "")).strip()

    return {
        "title": title,
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
        "venue": venue,
        "locality": str(address.get("addressLocality", "")).strip(),
        "region": str(address.get("addressRegion", "")).strip(),
        "address": str(address.get("streetAddress", "")).strip(),
        "price": offer.get("price", ""),
        "currency": offer.get("priceCurrency", ""),
        "image": normalize_url(image[0]) if image else "",
        "url": event.get("url", ""),
        "categories": tag_event(title, venue),
    }


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def scrape(max_pages: int, days: int, limit: int) -> list[dict]:
    print(f"Scanning Quicket (up to {max_pages} page(s), next {days} day(s), limit {limit})...")
    now = datetime.now(LOCAL_TZ)
    window_end = now + timedelta(days=days)
    by_url: dict[str, dict] = {}

    for page in range(1, max_pages + 1):
        print(f"  Page {page}/{max_pages} — {len(by_url)} event(s) so far...")
        for event in extract_events(fetch_page(page)):
            start = parse_dt(event.get("startDate"))
            end = parse_dt(event.get("endDate")) or start
            if not start or not end:
                continue
            if start < now or start > window_end:
                continue
            if not is_cape_town_event(event):
                continue
            summary = event_summary(event)
            if is_excluded_event(summary["title"], summary["venue"]):
                continue
            print(f"    Processing event: {summary['title'] or summary['url']}")
            location_key = ", ".join(
                part for part in [summary.get("address", ""), summary.get("venue", ""), summary.get("locality", ""), summary.get("region", ""), "South Africa"]
                if part
            ).strip()
            summary["location_key"] = location_key
            summary["missing_location"] = not bool(location_key)
            summary["place_key"] = ""
            summary["missing_place"] = True
            by_url[summary["url"]] = summary
        if limit > 0 and len(by_url) >= limit:
            print(f"  Limit of {limit} reached on page {page}.")
            break

    results = sorted(by_url.values(), key=lambda item: item["start"])
    if limit > 0:
        results = results[:limit]
    print(f"Scraped {len(results)} Quicket event(s).")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape recent Cape Town events from Quicket.")
    parser.add_argument("--pages", type=int, default=30, help="How many Quicket list pages to scan.")
    parser.add_argument("--days", type=int, default=365, help="How many days ahead to include.")
    parser.add_argument("--limit", type=int, default=EVENTS_MAX_ITEMS, help="Maximum number of matching events to keep (0 = no limit).")
    parser.add_argument("--hard", action="store_true", help="Recreate this source output from scratch before writing.")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.hard and JSON_OUTPUT.exists():
        print(f"Removing stale Quicket output: {JSON_OUTPUT}")
        JSON_OUTPUT.unlink()
    events = scrape(max_pages=args.pages, days=args.days, limit=args.limit)
    JSON_OUTPUT.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    sync_events_data_to_docs()
    print(f"Wrote {len(events)} Quicket event(s) to {JSON_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

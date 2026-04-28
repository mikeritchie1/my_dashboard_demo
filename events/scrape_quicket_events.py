from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


BASE_URL = "https://www.quicket.co.za/events/{page}/"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
JSON_OUTPUT = OUTPUT_DIR / "quicket_events.json"
TEXT_OUTPUT = OUTPUT_DIR / "quicket_events.txt"
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

    return {
        "title": event.get("name", "").strip(),
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
        "venue": str(location.get("name", "")).strip(),
        "locality": str(address.get("addressLocality", "")).strip(),
        "region": str(address.get("addressRegion", "")).strip(),
        "address": str(address.get("streetAddress", "")).strip(),
        "price": offer.get("price", ""),
        "currency": offer.get("priceCurrency", ""),
        "image": normalize_url(image[0]) if image else "",
        "url": event.get("url", ""),
    }


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def format_date(value: str) -> str:
    if not value:
        return "Date unknown"
    return datetime.fromisoformat(value).strftime("%a %d %b, %H:%M")


def write_text(events: list[dict], days: int, limit: int) -> None:
    lines = [f"Quicket Cape Town events - next {min(limit, len(events))} found within {days} days", ""]
    if not events:
        lines.append("No matching events found.")
    for index, event in enumerate(events, start=1):
        price = event["price"]
        price_text = "Free/price not listed" if price in ("", 0, 0.0) else f"{event['currency']} {price}"
        lines.extend(
            [
                f"{index}. {event['title']}",
                f"   When: {format_date(event['start'])}",
                f"   Where: {event['venue']} ({event['locality']})",
                f"   Price: {price_text}",
                f"   Link: {event['url']}",
                "",
            ]
        )
    TEXT_OUTPUT.write_text("\n".join(lines), encoding="utf-8")


def scrape(max_pages: int, days: int, limit: int) -> list[dict]:
    now = datetime.now(LOCAL_TZ)
    window_end = now + timedelta(days=days)
    by_url: dict[str, dict] = {}

    for page in range(1, max_pages + 1):
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
            by_url[summary["url"]] = summary
        if len(by_url) >= limit:
            break

    return sorted(by_url.values(), key=lambda item: item["start"])[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape recent Cape Town events from Quicket.")
    parser.add_argument("--pages", type=int, default=30, help="How many Quicket list pages to scan.")
    parser.add_argument("--days", type=int, default=365, help="How many days ahead to include.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of matching events to keep.")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events = scrape(max_pages=args.pages, days=args.days, limit=args.limit)
    JSON_OUTPUT.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    write_text(events, args.days, args.limit)
    print(f"Wrote {len(events)} Quicket event(s) to {JSON_OUTPUT}")
    print(f"Wrote readable list to {TEXT_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

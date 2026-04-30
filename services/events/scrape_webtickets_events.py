from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


BASE_URL = env_get("SCRAPE_WEBTICKETS_CATEGORY_URL_TEMPLATE", "https://www.webtickets.co.za/v2/category.aspx?itemid=1184162&location=9&when=anytime&page={page}")
PAGE_PREFIX = env_get("SCRAPE_WEBTICKETS_PAGE_PREFIX", "https://www.webtickets.co.za/v2/")
REPO_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_DIR / "data" / "events"
JSON_OUTPUT = OUTPUT_DIR / "webtickets_wc_events.json"


def fetch_page(page: int) -> str:
    request = urllib.request.Request(
        BASE_URL.format(page=page),
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; my-dashboard/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def abs_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{PAGE_PREFIX}{url.lstrip('/')}"


def parse_total_pages(page_html: str) -> int:
    matches = re.findall(r"when=anytime&amp;page=(\d+)", page_html)
    if not matches:
        return 1
    return max(int(value) for value in matches)


def extract_events(page_html: str) -> list[dict]:
    cards = re.findall(r'<div class="product-card mb-30">(.*?)</div>\s*</div><div class="col-md-4 col-sm-6">', page_html, flags=re.DOTALL)
    events: list[dict] = []
    for card in cards:
        link_match = re.search(r'<a href="(event\.aspx\?itemid=\d+)" class="spinner">', card)
        title_match = re.search(r'<h3 class="product-card-title">\s*<a class="spinner" href="[^"]+">(.*?)</a>', card, flags=re.DOTALL)
        image_match = re.search(r'<img src="([^"]+)" alt="', card)
        date_match = re.search(r'<div class="product-card-meta">(.*?)</div>', card, flags=re.DOTALL)
        venue_match = re.search(r'<ul class="product-card-category"><li>(.*?)</li></ul>', card, flags=re.DOTALL)
        price_match = re.search(r'<div class="product-card-price">(.*?)</div>', card, flags=re.DOTALL)

        if not link_match or not title_match:
            continue

        events.append(
            {
                "title": html.unescape(title_match.group(1)).strip(),
                "url": abs_url(link_match.group(1).strip()),
                "image": abs_url(image_match.group(1).strip()) if image_match else "",
                "date_text": html.unescape(date_match.group(1)).strip() if date_match else "",
                "venue": html.unescape(venue_match.group(1)).strip() if venue_match else "",
                "price": html.unescape(price_match.group(1)).strip() if price_match else "",
                "source": "Webtickets",
                "region": "Western Cape",
            }
        )
    return events


def scrape(limit: int) -> list[dict]:
    first_page = fetch_page(1)
    total_pages = parse_total_pages(first_page)
    all_events: list[dict] = []
    seen_urls: set[str] = set()

    for page in range(1, total_pages + 1):
        page_html = first_page if page == 1 else fetch_page(page)
        for event in extract_events(page_html):
            if event["url"] in seen_urls:
                continue
            seen_urls.add(event["url"])
            all_events.append(event)
            if len(all_events) >= limit:
                return all_events
    return all_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Webtickets Western Cape events.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of events to collect.")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events = scrape(limit=args.limit)
    JSON_OUTPUT.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(events)} Webtickets event(s) to {JSON_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

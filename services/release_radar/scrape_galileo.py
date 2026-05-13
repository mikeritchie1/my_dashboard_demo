from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


GALILEO_MOVIES_URL = env_get("SCRAPE_GALILEO_MOVIES_URL", "https://thegalileo.co.za/movies/")
DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "galileo_movies.json"
DEFAULT_TIMEOUT = 30


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; my-dashboard/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-ZA,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def absolute_url(url: str, base_url: str = GALILEO_MOVIES_URL) -> str:
    return urllib.parse.urljoin(base_url, html.unescape(url.strip()))


def clean_text(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<svg\b[^>]*>.*?</svg>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def first_match(pattern: str, text: str, flags: int = re.IGNORECASE | re.DOTALL) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def parse_label_value_spans(block: str) -> dict[str, str]:
    values: dict[str, str] = {}
    spans = re.findall(r"<span\b[^>]*>(.*?)</span>", block, flags=re.IGNORECASE | re.DOTALL)
    pending_label = ""
    for raw_span in spans:
        text = clean_text(raw_span)
        if not text:
            continue
        if text.endswith(":"):
            pending_label = text[:-1].strip().lower().replace(" ", "_")
            continue
        if text.startswith("Day:"):
            values["day"] = text.split(":", 1)[1].strip()
            continue
        if pending_label:
            values[pending_label] = text
            pending_label = ""
    return values


def parse_listing_movies(page_html: str) -> list[dict[str, str]]:
    movies: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for block_match in re.finditer(
        r'<li class="wcs-class">(.*?)</li>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        block = block_match.group(1)
        url = first_match(r'<a\b[^>]*class="[^"]*\bwcs-btn\b[^"]*"[^>]*href="([^"]+)"', block)
        title = first_match(
            r'<h3\b[^>]*class="[^"]*\btitledesktop\b[^"]*"[^>]*>(.*?)</h3>',
            block,
        ) or first_match(r'<h3\b[^>]*class="[^"]*\btitlembile\b[^"]*"[^>]*>(.*?)</h3>', block)
        date_text = first_match(r'<time\b[^>]*datetime="([^"]+)"', block)

        if not title or not url:
            continue

        url = absolute_url(url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        info = parse_label_value_spans(block)
        movies.append(
            {
                "title": clean_text(title),
                "date_text": clean_text(date_text),
                "day": info.get("day", ""),
                "venue": info.get("venue", ""),
                "doors_open": info.get("doors_open", ""),
                "movie_starts": info.get("movie_starts", ""),
                "genre": info.get("genre", ""),
                "age_restriction": info.get("age_restriction", ""),
                "url": url,
            }
        )

    return movies


def parse_detail_table(detail_html: str) -> dict[str, str]:
    details: dict[str, str] = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", detail_html, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 2:
            continue
        label = clean_text(cells[0]).rstrip(":").lower().replace(" ", "_")
        value = clean_text(cells[1])
        if label and value:
            details[label] = value
    return details


def button_link_by_text(page_html: str, text_pattern: str) -> str:
    for match in re.finditer(
        r'(<a\b[^>]*class="[^"]*\belementor-button-link\b[^"]*"[^>]*href="([^"]+)"[^>]*>.*?</a>)',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        button_html, href = match.groups()
        if re.search(text_pattern, clean_text(button_html), flags=re.IGNORECASE):
            return href.strip()
    return ""


def parse_detail_page(detail_html: str, url: str) -> dict[str, str]:
    title = clean_text(first_match(r"<h1\b[^>]*>(.*?)</h1>", detail_html))
    image = first_match(
        r'<img\b[^>]*src="([^"]+)"[^>]*class="[^"]*attachment-large[^"]*"',
        detail_html,
    )
    synopsis = clean_text(first_match(r"(<p><strong>[^<]+</strong>.*?</p>)", detail_html))
    trailer_url = button_link_by_text(detail_html, r"\bmovie trailer\b")
    book_url = button_link_by_text(detail_html, r"\bbook\b")

    details = parse_detail_table(detail_html)
    parsed = {
        "detail_title": title,
        "image": absolute_url(image, url) if image else "",
        "synopsis": synopsis,
        "trailer_url": absolute_url(trailer_url, url) if trailer_url else "",
        "book_url": absolute_url(book_url, url) if book_url else "",
    }
    parsed.update(details)
    return parsed


def iso_date(date_text: str) -> str:
    raw = clean_text(date_text)
    if not raw:
        return ""
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def runtime_minutes(value: str) -> str:
    raw = clean_text(value).lower()
    if not raw:
        return ""
    hours = 0
    minutes = 0
    hour_match = re.search(r"(\d+)\s*h", raw)
    minute_match = re.search(r"(\d+)\s*m", raw)
    compact_minute_match = re.search(r"\d+\s*h\s*(\d{1,2})\b", raw)
    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))
    elif compact_minute_match:
        minutes = int(compact_minute_match.group(1))
    total = hours * 60 + minutes
    return str(total) if total else ""


def genre_list(value: str) -> list[str]:
    raw = clean_text(value)
    if not raw:
        return []
    # Galileo stores combined genre labels as plain text; keep the original label
    # intact so "Comedy Drama Fantasy" reads naturally in the detail drawer.
    return [raw]


def normalize_item(listing: dict[str, str], details: dict[str, str]) -> dict[str, object]:
    movie_date = details.get("movie_date") or listing.get("date_text", "")
    venue = details.get("movie_venue") or listing.get("venue", "")
    genre = details.get("genre") or listing.get("genre", "")
    run_time = details.get("run_time", "")
    age_restriction = details.get("age_restriction") or listing.get("age_restriction", "")
    image = details.get("image", "")
    synopsis = details.get("synopsis", "")

    return {
        "title": listing.get("title", ""),
        "detail_title": details.get("detail_title") or listing.get("title", ""),
        "url": listing.get("url", ""),
        "source": "The Galileo Open Air Cinema",
        "status": "open_air_cinema",
        "status_label": "Open air cinema",
        "release_date": iso_date(movie_date),
        "event_date_text": movie_date,
        "day": listing.get("day", ""),
        "venue": venue,
        "doors_open": details.get("doors_open") or listing.get("doors_open", ""),
        "movie_starts": details.get("movie_starts") or listing.get("movie_starts", ""),
        "cinema_type": details.get("cinema_type", ""),
        "age_restriction": age_restriction,
        "run_time": run_time,
        "runtime_minutes": runtime_minutes(run_time),
        "genre": genre,
        "genres": genre_list(genre),
        "overview": synopsis,
        "synopsis": synopsis,
        "image": image,
        "poster_url": image,
        "trailer_url": details.get("trailer_url", ""),
        "book_url": details.get("book_url", ""),
        "location_label": f"Playing at {venue}" if venue else "",
    }


def scrape_galileo(limit: int = 0) -> dict[str, object]:
    page_html = fetch_html(GALILEO_MOVIES_URL)
    listings = parse_listing_movies(page_html)
    if limit > 0:
        listings = listings[:limit]

    items: list[dict[str, object]] = []
    for listing in listings:
        detail_html = fetch_html(listing["url"])
        details = parse_detail_page(detail_html, listing["url"])
        items.append(normalize_item(listing, details))

    items.sort(key=lambda item: (str(item.get("release_date") or "9999-12-31"), str(item.get("title") or "")))
    return {
        "source": GALILEO_MOVIES_URL,
        "theatre": "The Galileo Open Air Cinema",
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape The Galileo open-air cinema movie events.")
    parser.add_argument("--hard", action="store_true", help="Remove existing Galileo output before scraping.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum movie events to collect.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    args = parser.parse_args()

    if args.hard and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    payload = scrape_galileo(limit=args.limit)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload.get('items', []))} Galileo movie event(s) to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

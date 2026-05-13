from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get

from scrape_releases import fetch_tmdb_details


IMAX_THEATRE_URL = env_get(
    "SCRAPE_IMAX_WATERFRONT_URL",
    "https://www.imax.com/en/za/theatre/ster-kinekor-va-waterfront-imax",
)
IMAX_FALLBACK_URL = env_get(
    "SCRAPE_IMAX_WATERFRONT_FALLBACK_URL",
    "https://r.jina.ai/http://www.imax.com/en/za/theatre/ster-kinekor-va-waterfront-imax",
)
COMING_SOON_LIMIT = max(0, int(env_get("SCRAPE_IMAX_COMING_SOON_LIMIT", "4") or "4"))
DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "imax_waterfront.json"


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_theatre_text() -> tuple[str, str]:
    try:
        return fetch_text(IMAX_THEATRE_URL), IMAX_THEATRE_URL
    except urllib.error.HTTPError as error:
        if error.code != 403:
            raise
        return fetch_text(IMAX_FALLBACK_URL), IMAX_FALLBACK_URL


def fallback_url(url: str) -> str:
    return "https://r.jina.ai/" + url.replace("https://", "http://", 1)


def parse_theatre_listings(text: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    listings: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for line in lines:
        title_match = re.match(r"^##\s+\[(.+?)>\]\((http://www\.imax\.com/en/za/movie/[^)]+)\)", line)
        if title_match:
            if current:
                listings.append(current)
            current = {
                "title": title_match.group(1).strip(),
                "url": title_match.group(2).strip(),
                "format": "",
                "showtimes": [],
            }
            continue

        if not current:
            continue

        if line.upper().startswith("IMAX "):
            current["format"] = line
            continue

        time_match = re.match(r"^\[([0-2]\d:[0-5]\d)\]\(http://www\.imax\.com/en/za/ticket-partner\)$", line)
        if time_match:
            showtimes = current.get("showtimes")
            if isinstance(showtimes, list):
                showtimes.append(time_match.group(1))

    if current:
        listings.append(current)
    return listings


def parse_related_movies(text: str, excluded_urls: set[str]) -> list[dict[str, str]]:
    seen_urls: set[str] = set()
    movies: list[dict[str, str]] = []
    for match in re.finditer(r"\[([^\]]+?)>\]\((http://www\.imax\.com/en/za/movie/[^)]+)\)", text):
        title = match.group(1).strip()
        url = match.group(2).strip()
        if url in seen_urls or url in excluded_urls:
            continue
        seen_urls.add(url)
        movies.append({"title": title, "url": url})
    return movies


def parse_coming_soon_from_current_movies(listings: list[dict[str, object]]) -> list[dict[str, str]]:
    excluded_urls = {str(movie.get("url", "")).strip() for movie in listings if str(movie.get("url", "")).strip()}
    coming_soon: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for movie in listings:
        movie_url = str(movie.get("url", "")).strip()
        if not movie_url:
            continue
        movie_text = fetch_text(fallback_url(movie_url))
        for related in parse_related_movies(movie_text, excluded_urls):
            if related["url"] in seen_urls:
                continue
            seen_urls.add(related["url"])
            coming_soon.append(related)
            if COMING_SOON_LIMIT and len(coming_soon) >= COMING_SOON_LIMIT:
                return coming_soon
    return coming_soon


def tmdb_search_title(title: str) -> str:
    if title == "Top Gun: 40th Anniversary":
        return "Top Gun"
    return title


def enrich_item(base: dict[str, object], status: str) -> dict[str, object]:
    title = str(base.get("title") or "").strip()
    details = fetch_tmdb_details(tmdb_search_title(title))
    item: dict[str, object] = {
        **details,
        "title": title,
        "url": str(base.get("url") or details.get("tmdb_url") or "").strip(),
        "source": "IMAX Waterfront",
        "status": status,
        "status_label": "Now playing" if status == "now_playing" else "Coming soon",
        "showtimes": base.get("showtimes") if isinstance(base.get("showtimes"), list) else [],
        "format": str(base.get("format") or "").strip(),
    }
    poster = str(item.get("poster_url") or "").strip()
    if poster:
        item["image"] = poster
    if not item.get("release_date"):
        item["release_date"] = ""
    return item


def sort_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    def key(item: dict[str, object]) -> tuple[int, str, str]:
        status_rank = 0 if item.get("status") == "now_playing" else 1
        return (status_rank, str(item.get("release_date") or "9999-12-31"), str(item.get("title") or ""))

    return sorted(items, key=key)


def scrape_imax() -> dict:
    theatre_text, source = fetch_theatre_text()
    now_playing = parse_theatre_listings(theatre_text)
    coming_soon = parse_coming_soon_from_current_movies(now_playing)

    items: list[dict[str, object]] = []
    for movie in now_playing:
        items.append(enrich_item(movie, "now_playing"))
    for movie in coming_soon:
        item = enrich_item(movie, "coming_soon")
        items.append(item)

    return {
        "source": source,
        "theatre": "Ster-Kinekor V&A Waterfront IMAX",
        "items": sort_items(items),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape IMAX Waterfront now-playing and coming-soon films.")
    parser.add_argument("--hard", action="store_true", help="Remove existing IMAX output before scraping.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum coming-soon IMAX items. 0 uses configured default.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    args = parser.parse_args()

    global COMING_SOON_LIMIT
    if args.limit > 0:
        COMING_SOON_LIMIT = args.limit
    if args.hard and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    payload = scrape_imax()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload.get('items', []))} IMAX Waterfront item(s) to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

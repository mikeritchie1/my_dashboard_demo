from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from services.release_radar.scrape_releases import fetch_tmdb_details


CLIENT_URL = "https://www.webtickets.co.za/v2/client.aspx?clientcode=labia"
EVENT_URL_TEMPLATE = "https://www.webtickets.co.za/v2/event.aspx?itemid={itemid}"
DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "labia_showtimes.json"


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


def parse_cards(client_html: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'(?s)<a href="event\.aspx\?itemid=(\d+)" class="spinner">\s*'
        r'<img src="([^"]+)"[^>]*>\s*</a>.*?'
        r'<div class="product-card-meta">From\s*([^<]+)</div>\s*'
        r'<h3 class="product-card-title">\s*<a class="spinner" href="event\.aspx\?itemid=\d+">([^<]+)</a>'
    )
    cards: list[dict[str, str]] = []
    for match in pattern.finditer(client_html):
        itemid = match.group(1).strip()
        image = match.group(2).strip()
        from_text = match.group(3).strip()
        title = re.sub(r"\s+", " ", match.group(4)).strip()
        if "VOUCHER" in title.upper():
            continue
        cards.append({"from_text": from_text, "itemid": itemid, "title": title, "image": image})
    return cards


def parse_event_dates(event_html: str, itemid: str) -> list[date]:
    pattern = re.compile(rf"setPerformance\({re.escape(itemid)},0,'([0-9]{{1,2}}-[A-Za-z]{{3}}-[0-9]{{4}})'\)")
    days: list[date] = []
    for match in pattern.finditer(event_html):
        day = datetime.strptime(match.group(1), "%d-%b-%Y").date()
        days.append(day)
    return sorted(set(days))


def tmdb_search_title(title: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", title)
    cleaned = re.sub(r"\bAfrikaans with English subtitles\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:-")
    return cleaned or title


def labia_week_start(day: date) -> date:
    # Labia schedules are published in Friday -> Thursday windows.
    return day - timedelta(days=(day.weekday() - 4) % 7)


def scrape_labia_showtimes(start_date: date, days: int) -> dict[str, object]:
    if days == 14:
        first_week_start = labia_week_start(start_date)
        end_date = first_week_start + timedelta(days=13)
        start_date = first_week_start
    else:
        end_date = start_date + timedelta(days=max(1, days) - 1)

    client_html = fetch_text(CLIENT_URL)
    cards = parse_cards(client_html)

    grouped: dict[str, dict[str, object]] = {}
    for card in cards:
        from_dt = datetime.strptime(card["from_text"], "%d %b %Y %H:%M")
        show_time = from_dt.strftime("%H:%M")
        event_url = EVENT_URL_TEMPLATE.format(itemid=card["itemid"])
        event_html = fetch_text(event_url)
        event_days = parse_event_dates(event_html, card["itemid"])
        movie_key = tmdb_search_title(card["title"]).lower()
        if movie_key not in grouped:
            grouped[movie_key] = {
                "title": card["title"],
                "tmdb_search_title": tmdb_search_title(card["title"]),
                "image": card.get("image", ""),
                "book_urls": set(),
                "itemids": set(),
                "times_by_date": {},
            }

        bucket = grouped[movie_key]
        bucket["book_urls"].add(event_url)
        bucket["itemids"].add(card["itemid"])

        for day in event_days:
            if not (start_date <= day <= end_date):
                continue
            key = day.isoformat()
            date_times = bucket["times_by_date"].setdefault(key, set())
            date_times.add(show_time)

    items: list[dict[str, object]] = []
    for grouped_movie in grouped.values():
        times_by_date = grouped_movie["times_by_date"]
        if not times_by_date:
            continue

        sorted_dates = sorted(times_by_date)
        showings: list[str] = []
        showings_by_date: list[dict[str, object]] = []
        for day_key in sorted_dates:
            sorted_times = sorted(times_by_date[day_key])
            showings_by_date.append({"date": day_key, "times": sorted_times})
            for t in sorted_times:
                showings.append(f"{day_key} {t}")

        first_day = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
        last_day = datetime.strptime(sorted_dates[-1], "%Y-%m-%d").date()
        event_date_text = (
            first_day.strftime("%d %b %Y")
            if first_day == last_day
            else f"{first_day.strftime('%d %b %Y')} - {last_day.strftime('%d %b %Y')}"
        )

        details = fetch_tmdb_details(grouped_movie["tmdb_search_title"], year=str(first_day.year))
        if not details:
            details = fetch_tmdb_details(grouped_movie["tmdb_search_title"])

        book_url = sorted(grouped_movie["book_urls"])[0]
        itemid = sorted(grouped_movie["itemids"])[0]
        items.append(
            {
                **details,
                "title": grouped_movie["title"],
                "itemid": itemid,
                "source": "Labia Theatre",
                "status": "now_showing",
                "status_label": "Now showing",
                "url": book_url,
                "book_url": book_url,
                "event_date_text": event_date_text,
                "release_date": details.get("release_date", "") or first_day.isoformat(),
                "image": details.get("poster_url", "") or grouped_movie.get("image", ""),
                "showings": showings,
                "showings_by_date": showings_by_date,
            }
        )

    items.sort(key=lambda item: (str(item.get("event_date_text", "")), str(item.get("title", ""))))
    return {
        "source": CLIENT_URL,
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": max(1, days),
        },
        "weeks": [
            {
                "start_date": start_date.isoformat(),
                "end_date": (start_date + timedelta(days=6)).isoformat(),
            },
            {
                "start_date": (start_date + timedelta(days=7)).isoformat(),
                "end_date": (start_date + timedelta(days=13)).isoformat(),
            },
        ] if days == 14 else [],
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Labia Theatre showtimes from Webtickets.")
    parser.add_argument("--hard", action="store_true", help="Remove existing output before scraping.")
    parser.add_argument("--days", type=int, default=14, help="Number of days from --start-date to include.")
    parser.add_argument("--start-date", default=date.today().isoformat(), help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()

    if args.hard and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    payload = scrape_labia_showtimes(start_date=start_date, days=args.days)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload.get('items', []))} Labia title(s) to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

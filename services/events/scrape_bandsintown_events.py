from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get
from event_tags import is_excluded_event, tag_event


SOURCE_URL = env_get("SCRAPE_BANDSINTOWN_EVENTS_URL", "https://www.bandsintown.com/c/cape-town-south-africa")
# 0 means no hard limit: scrape all discoverable events.
EVENTS_MAX_ITEMS = int(env_get("SCRAPE_BANDSINTOWN_MAX_ITEMS", "0"))
MAX_PAGES = max(1, int(env_get("SCRAPE_BANDSINTOWN_MAX_PAGES", "30")))
REPO_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_DIR / "data" / "events"
JSON_OUTPUT = OUTPUT_DIR / "bandsintown_events.json"
GENRE_FILTERS_PATH = OUTPUT_DIR / "bandsintown_genre_filters.json"
LOCAL_TZ = timezone(timedelta(hours=2), "SAST")
DEFAULT_GENRE_FILTERS = [
    "Alternative",
    "Blues",
    "Christian/Gospel",
    "Classical",
    "Country",
    "Comedy",
    "Electronic",
    "Folk",
    "Hip-Hop",
    "Jazz",
    "Latin",
    "Metal",
    "Pop",
    "Punk",
    "R&B/Soul",
    "Reggae",
    "Rock",
]


def genre_url(genre: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(genre or "").strip().lower()).strip("-")
    if not slug:
        return SOURCE_URL
    return f"https://www.bandsintown.com/all-dates/genre/{slug}#search"


def genre_fallback_url(genre: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(genre or "").strip().lower()).strip("-")
    if not slug:
        return SOURCE_URL
    return f"https://www.bandsintown.com/genre/{slug}#search"


def load_genre_filters() -> list[str]:
    if GENRE_FILTERS_PATH.exists():
        try:
            payload = json.loads(GENRE_FILTERS_PATH.read_text(encoding="utf-8"))
            values = payload.get("genres", []) if isinstance(payload, dict) else []
            if isinstance(values, list):
                cleaned = [clean_text(str(value)) for value in values if clean_text(str(value))]
                if cleaned:
                    return cleaned
        except json.JSONDecodeError:
            pass
    return DEFAULT_GENRE_FILTERS[:]


def ordered_genres(tags: set[str], genre_order: list[str]) -> list[str]:
    order_map = {clean_text(genre).lower(): index for index, genre in enumerate(genre_order)}
    unique_tags = list(dict.fromkeys(clean_text(tag) for tag in tags if clean_text(tag)))
    unique_tags.sort(key=lambda value: (order_map.get(value.lower(), 10_000), value.lower()))
    return unique_tags


def is_western_cape_event(event: dict[str, object]) -> bool:
    locality = clean_text(str(event.get("locality", ""))).lower()
    region = clean_text(str(event.get("region", ""))).lower()
    address = clean_text(str(event.get("address", ""))).lower()
    venue = clean_text(str(event.get("venue", ""))).lower()
    text = " ".join([locality, region, address, venue])
    if "western cape" in text or "cape town" in text:
        return True
    # Common nearby city labels that still belong to Western Cape listings.
    for token in ["stellenbosch", "paarl", "somerset west", "durbanville", "franschhoek", "fish hoek", "langa"]:
        if token in text:
            return True
    return False


class BandsintownCityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_anchor = False
        self.current_href = ""
        self.current_text: list[str] = []
        self.current_image = ""
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "a":
            href = attributes.get("href", "")
            if "/e/" in href:
                self.in_anchor = True
                self.current_href = href
                self.current_text = []
                self.current_image = ""
        elif tag == "img" and self.in_anchor:
            self.current_image = normalize_url(attributes.get("src", "") or attributes.get("data-src", ""))
            alt = attributes.get("alt", "")
            if alt:
                self.current_text.append(alt)

    def handle_data(self, data: str) -> None:
        if self.in_anchor:
            text = data.strip()
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.in_anchor:
            return
        text = clean_text(" ".join(self.current_text))
        if self.current_href and text:
            self.links.append(
                {
                    "url": normalize_url(self.current_href),
                    "text": text,
                    "image": self.current_image,
                }
            )
        self.in_anchor = False
        self.current_href = ""
        self.current_text = []
        self.current_image = ""


def clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", html.unescape(value or "")).strip()
    if "Ã" in text or "Â" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    return text


def normalize_url(url: str) -> str:
    raw = html.unescape(str(url or "").strip())
    if not raw:
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return urllib.parse.urljoin(SOURCE_URL, raw)


def paged_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    parsed = urllib.parse.urlparse(base_url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; my-dashboard/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Referer": "https://www.bandsintown.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_city_links(page_html: str) -> list[dict[str, str]]:
    parser = BandsintownCityParser()
    parser.feed(page_html)
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in parser.links:
        url = link["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        links.append(link)
    return links


def json_ld_payloads(page_html: str) -> list[dict]:
    matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    payloads: list[dict] = []
    for match in matches:
        raw = html.unescape(match).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
        elif isinstance(parsed, list):
            payloads.extend(item for item in parsed if isinstance(item, dict))
    return payloads


def find_json_ld_event(page_html: str) -> dict:
    for payload in json_ld_payloads(page_html):
        candidates = []
        if payload.get("@graph") and isinstance(payload["@graph"], list):
            candidates.extend(item for item in payload["@graph"] if isinstance(item, dict))
        candidates.append(payload)
        for item in candidates:
            event_type = item.get("@type")
            event_types = event_type if isinstance(event_type, list) else [event_type]
            if "Event" in event_types or "MusicEvent" in event_types:
                return item
    return {}


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def first_image(value: object) -> str:
    if isinstance(value, str):
        return normalize_url(value)
    if isinstance(value, list):
        for item in value:
            image = first_image(item)
            if image:
                return image
    if isinstance(value, dict):
        return normalize_url(str(value.get("url") or value.get("contentUrl") or ""))
    return ""


def display_fallback_date(text: str) -> str:
    match = re.search(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?\s+-\s+\d{1,2}:\d{2}\s*(?:AM|PM)\b",
        text,
        flags=re.IGNORECASE,
    )
    return clean_text(match.group(0)) if match else ""


def split_artist_and_venue(title: str, venue: str) -> tuple[str, str]:
    clean_title = clean_text(title)
    clean_venue = clean_text(venue)
    marker = " @ "
    if marker not in clean_title:
        return clean_title, clean_venue
    artist, suffix = clean_title.rsplit(marker, 1)
    if not clean_venue:
        clean_venue = clean_text(suffix)
    if clean_venue and suffix.lower() == clean_venue.lower():
        return clean_text(artist), clean_venue
    return clean_title, clean_venue


def event_from_json_ld(payload: dict, fallback: dict[str, str], forced_genres: list[str] | None = None) -> dict:
    location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    address = location.get("address") if isinstance(location.get("address"), dict) else {}
    start = parse_dt(str(payload.get("startDate") or ""))
    title = clean_text(str(payload.get("name") or fallback.get("text") or ""))
    venue = clean_text(str(location.get("name") or ""))
    title, venue = split_artist_and_venue(title, venue)
    url = normalize_url(str(payload.get("url") or fallback.get("url") or ""))
    image = first_image(payload.get("image")) or fallback.get("image", "")
    locality = clean_text(str(address.get("addressLocality") or "Cape Town"))
    region = clean_text(str(address.get("addressRegion") or "Western Cape"))
    genre_tags = forced_genres[:] if forced_genres else []

    return {
        "title": title,
        "artist": title,
        "start": start.isoformat() if start else "",
        "date_text": display_fallback_date(fallback.get("text", "")),
        "venue": venue,
        "locality": locality,
        "region": region,
        "address": clean_text(str(address.get("streetAddress") or "")),
        "image": image,
        "url": url,
        "source": "Bandsintown",
        "genre": ", ".join(genre_tags),
        "genre_tags": genre_tags,
        "categories": tag_event(title, venue),
    }


def event_from_listing(link: dict[str, str]) -> dict:
    text = clean_text(link.get("text", ""))
    date_text = display_fallback_date(text)
    title = clean_text(text.replace(date_text, "")) if date_text else text
    title, venue = split_artist_and_venue(title, "")
    return {
        "title": title,
        "artist": title,
        "start": "",
        "date_text": date_text,
        "venue": venue,
        "locality": "Cape Town",
        "region": "Western Cape",
        "address": "",
        "image": link.get("image", ""),
        "url": link.get("url", ""),
        "source": "Bandsintown",
        "genre": "",
        "genre_tags": [],
        "categories": tag_event(title, ""),
    }


def collect_listing_links(source_url: str, max_pages: int) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen_listing_urls: set[str] = set()
    stale_pages = 0

    for page in range(1, max_pages + 1):
        url = paged_url(source_url, page)
        try:
            page_links = parse_city_links(fetch_html(url))
        except Exception:
            page_links = []
        before = len(seen_listing_urls)
        for entry in page_links:
            entry_url = entry.get("url", "")
            if not entry_url or entry_url in seen_listing_urls:
                continue
            seen_listing_urls.add(entry_url)
            links.append(entry)
        discovered = len(seen_listing_urls) - before
        print(f"  Listing page {page}: {len(page_links)} candidate(s), {discovered} new.")
        if discovered == 0:
            stale_pages += 1
            if stale_pages >= 2:
                break
        else:
            stale_pages = 0
    return links


def scrape(limit: int, max_pages: int, source_url: str, listing_only: bool = False, genre_seed: str = "") -> list[dict]:
    print(f"Scanning Bandsintown: {source_url}")
    links = collect_listing_links(source_url=source_url, max_pages=max_pages)

    print(f"  Found {len(links)} unique event link(s).")

    configured_genres = load_genre_filters()
    selected_genres = [clean_text(genre_seed)] if clean_text(genre_seed) else configured_genres
    genre_membership: dict[str, set[str]] = {}
    by_url: dict[str, dict[str, str]] = {str(link.get("url") or ""): link for link in links if str(link.get("url") or "")}

    for genre in selected_genres:
        genre_links = collect_listing_links(source_url=genre_url(genre), max_pages=max_pages)
        print(f"  Genre {genre}: {len(genre_links)} link(s).")
        for link in genre_links:
            url = str(link.get("url") or "").strip()
            if not url:
                continue
            by_url.setdefault(url, link)
            genre_membership.setdefault(url, set()).add(genre)

    events: list[dict] = []
    seen_urls: set[str] = set()
    for link in by_url.values():
        url = link.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        forced_genres = ordered_genres(genre_membership.get(url, set()), configured_genres)
        event = event_from_listing(link)
        event["genre_tags"] = forced_genres
        event["genre"] = ", ".join(forced_genres)
        if not listing_only:
            try:
                payload = find_json_ld_event(fetch_html(url))
                if payload:
                    event = event_from_json_ld(payload, link, forced_genres=forced_genres)
            except Exception:
                pass
        if not event.get("title") or is_excluded_event(event["title"], event.get("venue", "")):
            continue
        if not is_western_cape_event(event):
            continue
        events.append(event)
        if limit > 0 and len(events) >= limit:
            break
    print(f"Scraped {len(events)} Bandsintown event(s) across up to {max_pages} listing page(s).")
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Cape Town concerts from Bandsintown.")
    parser.add_argument("--limit", type=int, default=EVENTS_MAX_ITEMS, help="Maximum number of events to collect (0 = no limit).")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="Maximum listing pages to scan.")
    parser.add_argument("--genre", default="", help="Optional genre slug/name, e.g. metal, hip-hop, r-b-soul.")
    parser.add_argument("--source-url", default="", help="Optional full source URL override.")
    parser.add_argument("--listing-only", action="store_true", help="Only scrape listing page cards (faster, fewer fields).")
    args = parser.parse_args()

    selected_genre = args.genre.strip()
    source_url = args.source_url.strip() or (genre_url(selected_genre) if selected_genre else SOURCE_URL)
    print(f"Using source: {source_url}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events = scrape(
        limit=args.limit,
        max_pages=max(1, args.max_pages),
        source_url=source_url,
        listing_only=bool(args.listing_only),
        genre_seed=selected_genre,
    )
    JSON_OUTPUT.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(events)} Bandsintown event(s) to {JSON_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

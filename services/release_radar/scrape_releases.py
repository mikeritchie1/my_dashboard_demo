from __future__ import annotations

import html
import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


SOURCE_URL = env_get("SCRAPE_RELEASES_SOURCE_URL", "https://pahe.ink/")
TMDB_API_BASE_URL = env_get("SCRAPE_TMDB_API_BASE_URL", "https://api.themoviedb.org/3")
TMDB_IMAGE_BASE_URL = env_get("SCRAPE_TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/w342")
TMDB_SITE_MOVIE_BASE_URL = env_get("SCRAPE_TMDB_SITE_MOVIE_BASE_URL", "https://www.themoviedb.org/movie")
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "pahe_latest.json"
REPO_DIR = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"
FETCH_LIMIT = max(1, int(env_get("SCRAPE_RELEASES_FETCH_LIMIT", "10") or "10"))
MAX_ITEMS = max(FETCH_LIMIT, int(env_get("SCRAPE_RELEASES_MAX_ITEMS", "120") or "120"))


class PosterGridParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_grid = False
        self.grid_depth = 0
        self.current_link: dict[str, str] | None = None
        self.items: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}

        if tag == "section" and self._is_poster_grid(attributes):
            self.in_grid = True
            self.grid_depth = 1
            return

        if not self.in_grid:
            return

        self.grid_depth += 1
        if tag == "a" and attributes.get("href") and attributes.get("title"):
            raw_title = html.unescape(attributes["title"]).strip()
            self.current_link = {
                "title": clean_title(raw_title),
                "raw_title": raw_title,
                "url": attributes["href"],
            }
        elif tag == "img" and self.current_link and attributes.get("src"):
            self.items.append(
                {
                    **self.current_link,
                    "image": attributes["src"],
                }
            )
            self.current_link = None

    def handle_endtag(self, tag: str) -> None:
        if not self.in_grid:
            return

        self.grid_depth -= 1
        if self.grid_depth <= 0:
            self.in_grid = False

    @staticmethod
    def _is_poster_grid(attributes: dict[str, str]) -> bool:
        classes = attributes.get("class", "")
        return "pic-grid" in classes and "cat-box" in classes


def clean_title(value: str) -> str:
    title = html.unescape(value).strip()
    title = re.sub(r"\s+", " ", title)
    # Pahe titles usually look like: "Movie Name (2026) WEB-DL 480p, 720p & 1080p"
    # Keep only the movie name before the year/quality suffix.
    title = re.sub(r"\s*\(\d{4}\)\s*.*$", "", title).strip()
    return title.rstrip(" -._,")


def extract_year(value: str) -> str:
    match = re.search(r"\((\d{4})\)", html.unescape(value))
    return match.group(1) if match else ""


def local_secret(name: str) -> str:
    if not LOCAL_SECRETS_FILE.exists():
        return ""

    for line in LOCAL_SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def secret(name: str) -> str:
    value = env_get(name, "") or os.getenv(name, "") or local_secret(name)
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def scrape_latest(limit: int = FETCH_LIMIT) -> list[dict[str, str]]:
    parser = PosterGridParser()
    parser.feed(fetch_html(SOURCE_URL))
    return parser.items[:limit]


def scrape_rating(page_url: str) -> str:
    html_text = fetch_html(page_url)

    # Prefer explicit IMDb rating text when available.
    imdb_match = re.search(r"IMDb\s*[:\-]?\s*([0-9](?:\.[0-9])?)", html_text, flags=re.IGNORECASE)
    if imdb_match:
        return imdb_match.group(1)

    # Fallback: look for rating values next to "rating"/"Rated".
    generic_match = re.search(
        r"(?:rating|rated)\s*[:\-]?\s*([0-9](?:\.[0-9])?)\s*(?:/10)?",
        html_text,
        flags=re.IGNORECASE,
    )
    if generic_match:
        return generic_match.group(1)

    return ""


def tmdb_request(path: str, query_params: dict[str, str] | None = None) -> dict:
    bearer_token = secret("TMDB_BEARER_TOKEN")
    api_key = secret("TMDB_API_KEY")
    if bearer_token and not bearer_token.startswith("eyJ") and not api_key:
        api_key = bearer_token
        bearer_token = ""
    if not bearer_token and not api_key:
        return {}

    params = dict(query_params or {})
    if api_key:
        params["api_key"] = api_key
    query = urllib.parse.urlencode(params)
    url = f"{TMDB_API_BASE_URL}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}


def list_names(items: list[dict], key: str = "name", limit: int = 8) -> list[str]:
    values = [str(entry.get(key) or "").strip() for entry in items if isinstance(entry, dict)]
    return [value for value in values if value][:limit]


def fetch_tmdb_details(title: str, year: str = "") -> dict[str, str | int | list[str]]:
    search_query = {"query": title, "include_adult": "false", "language": "en-US"}
    if year.isdigit():
        search_query["year"] = year

    search_payload = tmdb_request("/search/movie", search_query)
    results = search_payload.get("results", []) if isinstance(search_payload, dict) else []
    if not isinstance(results, list) or not results:
        return {}

    first = results[0] if isinstance(results[0], dict) else {}
    movie_id = int(first.get("id") or 0)
    if not movie_id:
        return {}

    details = tmdb_request(f"/movie/{movie_id}", {"append_to_response": "credits,videos", "language": "en-US"})
    if not isinstance(details, dict) or not details:
        return {}

    credits = details.get("credits", {}) if isinstance(details.get("credits"), dict) else {}
    crew = credits.get("crew", []) if isinstance(credits.get("crew"), list) else []
    cast = credits.get("cast", []) if isinstance(credits.get("cast"), list) else []
    videos = details.get("videos", {}) if isinstance(details.get("videos"), dict) else {}
    video_items = videos.get("results", []) if isinstance(videos.get("results"), list) else []
    trailer = ""
    for entry in video_items:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("site") or "").lower() == "youtube" and str(entry.get("type") or "").lower() == "trailer":
            key = str(entry.get("key") or "").strip()
            if key:
                trailer = f"https://www.youtube.com/watch?v={key}"
                break

    directors = list_names([person for person in crew if str(person.get("job") or "").lower() == "director"])
    genres = list_names(details.get("genres", []) if isinstance(details.get("genres"), list) else [])
    actors = list_names(cast, limit=10)
    poster_path = str(details.get("poster_path") or "").strip()

    return {
        "tmdb_id": movie_id,
        "tmdb_url": f"{TMDB_SITE_MOVIE_BASE_URL}/{movie_id}",
        "tmdb_rating": str(details.get("vote_average") or "").strip(),
        "tmdb_votes": str(details.get("vote_count") or "").strip(),
        "release_date": str(details.get("release_date") or "").strip(),
        "overview": str(details.get("overview") or "").strip(),
        "runtime_minutes": str(details.get("runtime") or "").strip(),
        "genres": genres,
        "directors": directors,
        "actors": actors,
        "trailer_url": trailer,
        "poster_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else "",
    }


def load_existing_items() -> list[dict[str, str]]:
    if not OUTPUT_FILE.exists():
        return []
    try:
        payload = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def item_key(item: dict[str, str]) -> str:
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or "").strip()
    return url or title


def merge_items(new_items: list[dict[str, str]], existing_items: list[dict[str, str]], max_items: int) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*new_items, *existing_items]:
        key = item_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= max_items:
            break
    return merged


def write_latest(items: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SOURCE_URL,
        "items": items,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    global FETCH_LIMIT, MAX_ITEMS

    parser = argparse.ArgumentParser(description="Scrape latest movie releases from Pahe.")
    parser.add_argument("--hard", action="store_true", help="Recreate output from scratch before writing.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum fetched release items (0 = configured default).")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; Pahe source is not paged here.")
    args = parser.parse_args()

    if args.limit > 0:
        FETCH_LIMIT = args.limit
        MAX_ITEMS = max(FETCH_LIMIT, args.limit)
    if args.hard and OUTPUT_FILE.exists():
        print(f"Removing stale release radar output: {OUTPUT_FILE}")
        OUTPUT_FILE.unlink()

    existing_items = load_existing_items()
    existing_by_url = {
        str(item.get("url") or "").strip(): item
        for item in existing_items
        if str(item.get("url") or "").strip()
    }
    today = date.today().isoformat()

    new_items = scrape_latest(FETCH_LIMIT)
    for item in new_items:
        item_url = str(item.get("url") or "").strip()
        if not item_url:
            continue
        raw_title = str(item.get("raw_title") or item.get("title") or "")
        guessed_year = extract_year(raw_title)
        item["title"] = clean_title(raw_title)
        item.pop("raw_title", None)
        existing_item = existing_by_url.get(item_url, {})
        existing_rating = str(existing_item.get("rating") or "").strip() if isinstance(existing_item, dict) else ""
        if existing_rating:
            item["rating"] = existing_rating
        else:
            try:
                item["rating"] = scrape_rating(item_url)
            except Exception:
                item["rating"] = ""

        if isinstance(existing_item, dict):
            item["first_seen_at"] = str(existing_item.get("first_seen_at") or "").strip() or today
            for key in [
                "tmdb_id",
                "tmdb_url",
                "tmdb_rating",
                "tmdb_votes",
                "release_date",
                "overview",
                "runtime_minutes",
                "genres",
                "directors",
                "actors",
                "trailer_url",
                "poster_url",
            ]:
                if key in existing_item and existing_item.get(key):
                    item[key] = existing_item.get(key)
        else:
            item["first_seen_at"] = today

        if not item.get("tmdb_id"):
            details = fetch_tmdb_details(item["title"], guessed_year)
            if details:
                item.update(details)
                if str(item.get("tmdb_rating") or "").strip():
                    item["rating"] = str(item.get("tmdb_rating")).strip()

    items = merge_items(new_items, existing_items, MAX_ITEMS)
    for item in items:
        if isinstance(item, dict) and not str(item.get("first_seen_at") or "").strip():
            item["first_seen_at"] = today
    write_latest(items)
    print(f"Wrote {len(items)} release radar item(s) to {OUTPUT_FILE} (fetched {len(new_items)} new candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

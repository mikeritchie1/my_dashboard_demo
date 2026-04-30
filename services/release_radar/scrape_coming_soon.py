from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


API_URL = env_get("SCRAPE_TMDB_UPCOMING_API_URL", "https://api.themoviedb.org/3/movie/upcoming")
DISCOVER_API_URL = env_get("SCRAPE_TMDB_DISCOVER_API_URL", "https://api.themoviedb.org/3/discover/movie")
IMAGE_BASE_URL = env_get("SCRAPE_TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/w342")
TMDB_SITE_MOVIE_BASE_URL = env_get("SCRAPE_TMDB_SITE_MOVIE_BASE_URL", "https://www.themoviedb.org/movie")
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "coming_soon.json"
REPO_DIR = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"
FETCH_LIMIT = max(1, int(env_get("SCRAPE_COMING_SOON_FETCH_LIMIT", "10") or "10"))
MAX_ITEMS = max(FETCH_LIMIT, int(env_get("SCRAPE_COMING_SOON_MAX_ITEMS", "120") or "120"))
WINDOW_DAYS = max(1, int(env_get("SCRAPE_COMING_SOON_WINDOW_DAYS", "90") or "90"))
MAX_PAGES = max(1, int(env_get("SCRAPE_COMING_SOON_MAX_PAGES", "10") or "10"))
RELEASE_TYPES = env_get("SCRAPE_COMING_SOON_RELEASE_TYPES", "2|3") or "2|3"
COMING_SOON_REGION = (env_get("SCRAPE_COMING_SOON_REGION", "") or "").strip().upper()


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
    value = env_get(name, "") or local_secret(name)
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def fetch_coming_soon(page: int = 1, region: str = "", language: str = "en-US") -> dict:
    bearer_token = secret("TMDB_BEARER_TOKEN")
    api_key = secret("TMDB_API_KEY")
    if bearer_token and not bearer_token.startswith("eyJ") and not api_key:
        api_key = bearer_token
        bearer_token = ""
    if not bearer_token and not api_key:
        raise RuntimeError("Missing TMDB_BEARER_TOKEN or TMDB_API_KEY in environment/secrets.env")

    start = date.today()
    end = start + timedelta(days=WINDOW_DAYS)
    query_params = {
        "language": language,
        "page": page,
        "sort_by": "primary_release_date.asc",
        "include_adult": "false",
        "include_video": "false",
        "with_release_type": RELEASE_TYPES,
        "release_date.gte": start.isoformat(),
        "release_date.lte": end.isoformat(),
    }
    if region:
        query_params["region"] = region
        query_params["watch_region"] = region
    if api_key:
        query_params["api_key"] = api_key

    query = urllib.parse.urlencode(query_params)
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    request = urllib.request.Request(
        f"{DISCOVER_API_URL}?{query}",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def movie_url(movie_id: int) -> str:
    return f"{TMDB_SITE_MOVIE_BASE_URL}/{movie_id}"


def normalize_movies(results: list[dict], limit: int = FETCH_LIMIT) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for movie in results:
        poster_path = movie.get("poster_path")
        if not poster_path:
            continue
        items.append(
            {
                "title": movie.get("title") or movie.get("original_title") or "",
                "url": movie_url(int(movie["id"])),
                "image": IMAGE_BASE_URL + poster_path,
                "release_date": movie.get("release_date") or "",
            }
        )
        if len(items) >= limit:
            break
    return items


def parse_release_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def filter_by_window(items: list[dict[str, str]], window_days: int) -> list[dict[str, str]]:
    start = date.today()
    end = start + timedelta(days=window_days)
    filtered: list[dict[str, str]] = []
    for item in items:
        released = parse_release_date(str(item.get("release_date") or ""))
        if not released:
            continue
        if start <= released <= end:
            filtered.append(item)
    return filtered


def write_upcoming(items: list[dict[str, str]], source_dates: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": DISCOVER_API_URL,
        "dates": source_dates,
        "items": items,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_existing_payload() -> dict:
    if not OUTPUT_FILE.exists():
        return {}
    try:
        payload = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def item_key(item: dict[str, str]) -> str:
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or "").strip()
    date = str(item.get("release_date") or "").strip()
    return url or f"{title}|{date}"


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


def main() -> int:
    all_results: list[dict] = []
    dates: dict = {}
    for page in range(1, MAX_PAGES + 1):
        payload = fetch_coming_soon(page=page, region=COMING_SOON_REGION)
        dates = payload.get("dates") or dates
        all_results.extend(payload.get("results", []))
        candidate_items = normalize_movies(all_results, MAX_ITEMS)
        in_window_items = filter_by_window(candidate_items, WINDOW_DAYS)
        if len(in_window_items) >= MAX_ITEMS:
            break

    new_items = filter_by_window(normalize_movies(all_results, MAX_ITEMS), WINDOW_DAYS)[:MAX_ITEMS]
    existing_payload = load_existing_payload()
    existing_items = existing_payload.get("items", [])
    if not isinstance(existing_items, list):
        existing_items = []
    items = merge_items(new_items, existing_items, MAX_ITEMS)
    write_upcoming(items, dates)
    print(f"Wrote {len(items)} coming soon item(s) to {OUTPUT_FILE} (fetched {len(new_items)} new candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

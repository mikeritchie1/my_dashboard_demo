from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


API_URL = env_get("SCRAPE_TMDB_UPCOMING_API_URL", "https://api.themoviedb.org/3/movie/upcoming")
IMAGE_BASE_URL = env_get("SCRAPE_TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/w342")
TMDB_SITE_MOVIE_BASE_URL = env_get("SCRAPE_TMDB_SITE_MOVIE_BASE_URL", "https://www.themoviedb.org/movie")
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "coming_soon.json"
REPO_DIR = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"


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


def fetch_upcoming(page: int = 1, region: str = "", language: str = "en-US") -> dict:
    bearer_token = secret("TMDB_BEARER_TOKEN")
    api_key = secret("TMDB_API_KEY")
    if bearer_token and not bearer_token.startswith("eyJ") and not api_key:
        api_key = bearer_token
        bearer_token = ""
    if not bearer_token and not api_key:
        raise RuntimeError("Missing TMDB_BEARER_TOKEN or TMDB_API_KEY in environment/secrets.env")

    query_params = {
        "language": language,
        "page": page,
    }
    if region:
        query_params["region"] = region
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
        f"{API_URL}?{query}",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def movie_url(movie_id: int) -> str:
    return f"{TMDB_SITE_MOVIE_BASE_URL}/{movie_id}"


def normalize_movies(results: list[dict], limit: int = 10) -> list[dict[str, str]]:
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


def write_upcoming(items: list[dict[str, str]], source_dates: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": API_URL,
        "dates": source_dates,
        "items": items,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    all_results: list[dict] = []
    dates: dict = {}
    for page in range(1, 6):
        payload = fetch_upcoming(page=page, region="ZA")
        dates = payload.get("dates") or dates
        all_results.extend(payload.get("results", []))
        if len(normalize_movies(all_results)) >= 10:
            break

    items = normalize_movies(all_results)
    write_upcoming(items, dates)
    print(f"Wrote {len(items)} coming soon item(s) to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

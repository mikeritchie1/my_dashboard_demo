from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


NOTION_VERSION = "2022-06-28"
DEFAULT_WATCHLIST_PAGE_ID = "1d757df8191880aeb859c1402a2154c8"
DEFAULT_WATCHLIST_URL = "https://www.notion.so/My-Watchlist-1d757df8191880aeb859c1402a2154c8"

REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = DATA_DIR / "watchlist.json"
MOVIE_DETAILS_CACHE_FILE = DATA_DIR / "watchlist_movie_details.json"
DOCS_DATA_DIR = REPO_DIR / "docs" / "data"
DOCS_OUTPUT_FILE = DOCS_DATA_DIR / "watchlist.json"
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
TMDB_SITE_MOVIE_BASE = "https://www.themoviedb.org/movie"
MOVIE_DETAIL_FIELDS = {
    "tmdb_id",
    "rating",
    "poster_url",
    "release_date",
    "overview",
    "description",
    "runtime_minutes",
    "directors",
    "actors",
    "trailer_url",
    "genres",
    "tmdb_url",
}

TEXT_BLOCK_TYPES = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "quote",
    "callout",
    "toggle",
}


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
    return os.environ.get(name, "").strip() or local_secret(name)


def rich_text_plain(rich_text: list[dict]) -> str:
    return "".join(part.get("plain_text", "") for part in rich_text).strip()


def notion_request(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"https://api.notion.com/v1/{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def tmdb_request(path: str, token: str, query: dict[str, str] | None = None) -> dict:
    query_string = ""
    if query:
        query_string = "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        f"https://api.themoviedb.org/3/{path}{query_string}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def block_text(block: dict) -> str:
    block_type = block.get("type", "")
    if block_type not in TEXT_BLOCK_TYPES:
        return ""
    value = block.get(block_type, {}) or {}
    text = rich_text_plain(value.get("rich_text", []))
    if block_type == "to_do":
        checked = value.get("checked")
        prefix = "[x] " if checked else "[ ] "
        return f"{prefix}{text}".strip() if text else ""
    return text


def get_block_children(block_id: str, token: str) -> list[dict]:
    blocks: list[dict] = []
    cursor = ""
    while True:
        query = f"?page_size=100&start_cursor={cursor}" if cursor else "?page_size=100"
        payload = notion_request(f"blocks/{block_id}/children{query}", token)
        blocks.extend(payload.get("results", []))
        if not payload.get("has_more"):
            return blocks
        cursor = payload.get("next_cursor") or ""


def flatten_blocks(blocks: list[dict], token: str, depth: int = 0) -> list[tuple[dict, int]]:
    flattened: list[tuple[dict, int]] = []
    for block in blocks:
        flattened.append((block, depth))
        if block.get("has_children"):
            children = get_block_children(block.get("id", ""), token)
            flattened.extend(flatten_blocks(children, token, depth + 1))
    return flattened


def normalize_label(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_page_id() -> str:
    explicit = secret("NOTION_WATCHLIST_PAGE_ID").replace("-", "").strip()
    if explicit:
        return explicit
    url_value = secret("NOTION_WATCHLIST_PAGE_URL").strip()
    if url_value:
        match = re.search(r"([0-9a-fA-F]{32})", url_value.replace("-", ""))
        if match:
            return match.group(1)
    return DEFAULT_WATCHLIST_PAGE_ID


def is_year_heading(text: str) -> str:
    match = re.match(r"^(20\d{2})\b", text.strip())
    return match.group(1) if match else ""


def clean_title(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\[(?:x| )\]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\d+[\).\-\s]+", "", cleaned)
    cleaned = cleaned.strip("- ").strip()
    return cleaned


def movie_key(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title).strip().lower()
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return normalized


def parse_watchlist(flat_blocks: list[tuple[dict, int]]) -> dict:
    current_domain = "movie"
    in_currently_watching = False
    in_now_section = False
    in_must_watch = False
    active_year = ""
    years: dict[str, list[dict]] = {}
    current = {"movies": [], "series": []}

    for block, _depth in flat_blocks:
        block_type = block.get("type", "")
        text = block_text(block)
        if not text:
            continue

        normalized_text = clean_title(text)
        label = normalize_label(normalized_text)
        year = is_year_heading(text)

        if label in {"movies", "movie"}:
            current_domain = "movie"
            in_currently_watching = False
            in_now_section = False
            in_must_watch = False
            active_year = ""
            continue
        if label in {"series", "tv series", "tv shows", "shows"}:
            current_domain = "series"
            in_currently_watching = False
            in_now_section = False
            in_must_watch = False
            active_year = ""
            continue
        if "now watching" in label or "currently watching" in label:
            in_currently_watching = True
            in_now_section = False
            in_must_watch = False
            active_year = ""
            continue
        if label == "now":
            in_currently_watching = False
            in_now_section = True
            in_must_watch = False
            active_year = ""
            continue
        if in_now_section and label == "must watch":
            in_currently_watching = True
            in_must_watch = True
            active_year = ""
            continue
        if in_now_section and label == "maybe":
            in_currently_watching = False
            in_must_watch = False
            active_year = ""
            continue
        if year:
            in_currently_watching = False
            in_now_section = False
            in_must_watch = False
            active_year = year
            years.setdefault(active_year, [])
            continue

        if block_type not in {"bulleted_list_item", "numbered_list_item", "to_do", "paragraph"}:
            continue

        title = clean_title(text)
        if not title:
            continue

        if in_currently_watching and ((not in_now_section) or in_must_watch):
            if current_domain == "series":
                current["series"].append(title)
            else:
                current["movies"].append(title)
            continue

        if active_year:
            years.setdefault(active_year, []).append({"type": current_domain, "title": title})

    history_by_year: list[dict] = []
    for year in sorted(years.keys(), reverse=True):
        entries = years[year]
        if entries:
            history_by_year.append({"year": year, "entries": entries})

    return {
        "source": secret("NOTION_WATCHLIST_PAGE_URL").strip() or DEFAULT_WATCHLIST_URL,
        "currently_watching": current,
        "history_by_year": history_by_year,
    }


def load_movie_details_cache() -> dict[str, dict]:
    if not MOVIE_DETAILS_CACHE_FILE.exists():
        return {}
    try:
        payload = json.loads(MOVIE_DETAILS_CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def write_movie_details_cache(cache: dict[str, dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ordered = {key: cache[key] for key in sorted(cache.keys())}
    MOVIE_DETAILS_CACHE_FILE.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")


def write_payload(payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    OUTPUT_FILE.write_text(serialized, encoding="utf-8")
    DOCS_OUTPUT_FILE.write_text(serialized, encoding="utf-8")


def progress_bar(processed: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + ("-" * width) + "]"
    ratio = max(0.0, min(1.0, processed / total))
    filled = int(round(ratio * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def extract_movie_titles(payload: dict) -> list[str]:
    titles: list[str] = []
    current_movies = payload.get("currently_watching", {}).get("movies", [])
    if isinstance(current_movies, list):
        titles.extend(str(title).strip() for title in current_movies if str(title).strip())

    for group in payload.get("history_by_year", []):
        entries = group.get("entries", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if str(entry.get("type", "")).strip().lower() != "movie":
                continue
            title = str(entry.get("title", "")).strip()
            if title:
                titles.append(title)
    return sorted(set(titles))


def fetch_movie_detail(title: str, tmdb_token: str) -> dict:
    result = {"title": title}
    try:
        search_payload = tmdb_request(
            "search/movie",
            tmdb_token,
            {
                "query": title,
                "include_adult": "false",
                "language": "en-US",
                "page": "1",
            },
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return result

    results = search_payload.get("results", [])
    if not isinstance(results, list) or not results:
        return result
    first = results[0]
    tmdb_id = first.get("id")
    if not isinstance(tmdb_id, int):
        return result

    result["tmdb_id"] = tmdb_id

    try:
        details_payload = tmdb_request(
            f"movie/{tmdb_id}",
            tmdb_token,
            {
                "language": "en-US",
                "append_to_response": "credits,videos",
            },
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        details_payload = {}

    chosen = details_payload if isinstance(details_payload, dict) and details_payload else first
    poster_path = str(chosen.get("poster_path") or "").strip()
    vote_average = chosen.get("vote_average")
    release_date = str(chosen.get("release_date") or "").strip()
    overview = str(chosen.get("overview") or "").strip()
    runtime = chosen.get("runtime")

    credits = details_payload.get("credits", {}) if isinstance(details_payload, dict) else {}
    cast = credits.get("cast", []) if isinstance(credits, dict) else []
    crew = credits.get("crew", []) if isinstance(credits, dict) else []
    videos = details_payload.get("videos", {}) if isinstance(details_payload, dict) else {}
    video_results = videos.get("results", []) if isinstance(videos, dict) else []
    genres = details_payload.get("genres", []) if isinstance(details_payload, dict) else []

    directors = [
        str(person.get("name") or "").strip()
        for person in crew
        if str(person.get("job") or "").strip().lower() == "director" and str(person.get("name") or "").strip()
    ]
    actors = [
        str(person.get("name") or "").strip()
        for person in cast[:8]
        if str(person.get("name") or "").strip()
    ]
    trailer_url = ""
    for video in video_results:
        if str(video.get("site") or "").strip().lower() != "youtube":
            continue
        video_type = str(video.get("type") or "").strip().lower()
        if video_type not in {"trailer", "teaser"}:
            continue
        key = str(video.get("key") or "").strip()
        if key:
            trailer_url = f"https://www.youtube.com/watch?v={key}"
            break

    genre_names = [
        str(genre.get("name") or "").strip()
        for genre in genres
        if str(genre.get("name") or "").strip()
    ]

    if isinstance(vote_average, (int, float)):
        result["rating"] = round(float(vote_average), 1)
    else:
        result["rating"] = None
    result["poster_url"] = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else ""
    result["release_date"] = release_date
    result["overview"] = overview
    result["description"] = overview
    result["runtime_minutes"] = int(runtime) if isinstance(runtime, (int, float)) else None
    result["directors"] = list(dict.fromkeys(directors))
    result["actors"] = actors
    result["trailer_url"] = trailer_url
    result["genres"] = genre_names
    result["tmdb_url"] = f"{TMDB_SITE_MOVIE_BASE}/{tmdb_id}"
    return result


def merge_movie_details(existing: dict, fetched: dict) -> dict:
    merged = dict(existing)
    merged.setdefault("title", str(existing.get("title") or fetched.get("title") or "").strip())
    for key in MOVIE_DETAIL_FIELDS:
        if key in merged:
            continue
        merged[key] = fetched.get(key)
    return merged


def movie_detail_needs_fetch(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return True
    return any(field not in entry for field in MOVIE_DETAIL_FIELDS)


def enrich_payload_with_movie_details(payload: dict) -> dict:
    tmdb_token = secret("TMDB_BEARER_TOKEN")
    titles = extract_movie_titles(payload)
    keys_in_use = {movie_key(title) for title in titles if movie_key(title)}
    cache = load_movie_details_cache()

    # Remove cache entries no longer present in watchlist.
    cache = {key: value for key, value in cache.items() if key in keys_in_use}

    total = len(titles)
    processed = 0

    def persist(status: str, current_title: str) -> None:
        percent = int(round((processed / total) * 100)) if total else 100
        payload["movie_details"] = cache
        payload["enrichment_progress"] = {
            "status": status,
            "processed": processed,
            "total": total,
            "percent": percent,
            "current_title": current_title,
        }
        write_movie_details_cache(cache)
        write_payload(payload)

    persist("running", "")

    try:
        for title in titles:
            key = movie_key(title)
            source = "cached"
            if key:
                existing = cache.get(key, {"title": title})
                if movie_detail_needs_fetch(existing) and tmdb_token:
                    fetched = fetch_movie_detail(title, tmdb_token)
                    cache[key] = merge_movie_details(existing, fetched)
                else:
                    cache[key] = existing
                source = "fetched"
                if not movie_detail_needs_fetch(existing):
                    source = "cached"
            processed += 1
            persist("running", title)
            print(f"{progress_bar(processed, total)} {processed}/{total} {source}: {title}")
    except KeyboardInterrupt:
        persist("interrupted", "")
        print("Interrupted: partial watchlist details were saved.")
        return payload

    persist("completed", "")
    return payload


def scrape_watchlist() -> dict:
    token = secret("NOTION_TOKEN") or secret("NOTION_API_TOKEN")
    page_id = extract_page_id()
    page_url = secret("NOTION_WATCHLIST_PAGE_URL").strip() or DEFAULT_WATCHLIST_URL

    if not token:
        return {
            "source": page_url,
            "error": "Missing NOTION_TOKEN",
            "currently_watching": {"movies": [], "series": []},
            "history_by_year": [],
            "movie_details": {},
            "enrichment_progress": {"status": "idle", "processed": 0, "total": 0, "percent": 0, "current_title": ""},
        }

    try:
        root_blocks = get_block_children(page_id, token)
        flat = flatten_blocks(root_blocks, token, 0)
        payload = parse_watchlist(flat)
        payload["source"] = page_url
        payload["page_id"] = page_id
        return enrich_payload_with_movie_details(payload)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return {
            "source": page_url,
            "error": f"Notion API error {error.code}: {detail}",
            "currently_watching": {"movies": [], "series": []},
            "history_by_year": [],
            "movie_details": {},
            "enrichment_progress": {"status": "idle", "processed": 0, "total": 0, "percent": 0, "current_title": ""},
        }
    except urllib.error.URLError as error:
        return {
            "source": page_url,
            "error": f"Notion API network error: {error}",
            "currently_watching": {"movies": [], "series": []},
            "history_by_year": [],
            "movie_details": {},
            "enrichment_progress": {"status": "idle", "processed": 0, "total": 0, "percent": 0, "current_title": ""},
        }


def main() -> int:
    payload = scrape_watchlist()
    write_payload(payload)
    total_entries = sum(len(group.get("entries", [])) for group in payload.get("history_by_year", []))
    print(
        f"Wrote watchlist to {OUTPUT_FILE} "
        f"({len(payload.get('currently_watching', {}).get('movies', []))} current movies, "
        f"{len(payload.get('currently_watching', {}).get('series', []))} current series, "
        f"{total_entries} watched entries)"
    )
    if payload.get("error"):
        print(payload["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


NOTION_VERSION = "2022-06-28"
DEFAULT_WATCHLIST_PAGE_ID = "1d757df8191880aeb859c1402a2154c8"
DEFAULT_WATCHLIST_URL = "https://www.notion.so/My-Watchlist-1d757df8191880aeb859c1402a2154c8"

REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = DATA_DIR / "watchlist.json"
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"

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


def write_payload(payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
        }

    try:
        root_blocks = get_block_children(page_id, token)
        flat = flatten_blocks(root_blocks, token, 0)
        payload = parse_watchlist(flat)
        payload["source"] = page_url
        payload["page_id"] = page_id
        return payload
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return {
            "source": page_url,
            "error": f"Notion API error {error.code}: {detail}",
            "currently_watching": {"movies": [], "series": []},
            "history_by_year": [],
        }
    except urllib.error.URLError as error:
        return {
            "source": page_url,
            "error": f"Notion API network error: {error}",
            "currently_watching": {"movies": [], "series": []},
            "history_by_year": [],
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

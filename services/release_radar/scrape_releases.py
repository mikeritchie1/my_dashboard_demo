from __future__ import annotations

import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


SOURCE_URL = env_get("SCRAPE_RELEASES_SOURCE_URL", "https://pahe.ink/")
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "release_radar"
OUTPUT_FILE = DATA_DIR / "pahe_latest.json"
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
            self.current_link = {
                "title": clean_title(attributes["title"]),
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
    return re.sub(r"\s+", " ", title)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def scrape_latest(limit: int = FETCH_LIMIT) -> list[dict[str, str]]:
    parser = PosterGridParser()
    parser.feed(fetch_html(SOURCE_URL))
    return parser.items[:limit]


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
    new_items = scrape_latest(FETCH_LIMIT)
    existing_items = load_existing_items()
    items = merge_items(new_items, existing_items, MAX_ITEMS)
    write_latest(items)
    print(f"Wrote {len(items)} release radar item(s) to {OUTPUT_FILE} (fetched {len(new_items)} new candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import shutil
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path


PRODUCTS_URL = "https://en.onepiece-cardgame.com/products/"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "one_piece"
DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "one_piece"
OUTPUT_FILE = DATA_DIR / "products.json"


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
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_category(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key == "boosters":
        return "boosters"
    if key == "decks":
        return "decks"
    return "other"


def parse_products(html_text: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    pattern = re.compile(
        r'(?s)<li class="linkListColBox"[^>]*data-cat="([^"]+)"[^>]*>\s*'
        r'<a href="([^"]+)" class="linkListColItem">.*?'
        r'<h4 class="linkListColTitle">(.*?)</h4>.*?'
        r'<p class="linkListColDate"><span class="head">(.*?)</span><time class="newsDate"(?: datetime="([^"]*)")?>(.*?)</time></p>'
    )
    for match in pattern.finditer(html_text):
        category_raw = strip_html(match.group(1))
        url = strip_html(match.group(2))
        title = strip_html(match.group(3))
        date_label = strip_html(match.group(4))
        date_iso = strip_html(match.group(5))
        date_text = strip_html(match.group(6))
        if not title:
            continue
        if url.startswith("/"):
            url = f"https://en.onepiece-cardgame.com{url}"

        release_date = ""
        if date_iso:
            release_date = date_iso
        else:
            # Fallback parser for month-only labels if datetime is absent.
            parsed = None
            for fmt in ("%B %d, %Y", "%B %Y"):
                try:
                    parsed = datetime.strptime(date_text, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed:
                release_date = parsed.isoformat()

        items.append(
            {
                "title": title,
                "category": normalize_category(category_raw),
                "category_label": "BOOSTERS" if normalize_category(category_raw) == "boosters" else (
                    "DECKS" if normalize_category(category_raw) == "decks" else "OTHER"
                ),
                "date_label": date_label,
                "release_date": release_date,
                "release_date_text": date_text,
                "url": url,
            }
        )
    return items


def parse_total_pages(html_text: str) -> int:
    max_page = 1
    for match in re.finditer(r'class="pageBtn[^"]*">\s*(\d+)\s*<', html_text):
        try:
            value = int(match.group(1))
        except ValueError:
            continue
        if value > max_page:
            max_page = value
    return max_page


def page_url(base_url: str, page: int) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    rebuilt = parsed._replace(query=urllib.parse.urlencode(query))
    return urllib.parse.urlunparse(rebuilt)


def scrape_pages(base_url: str, pages: int = 0) -> tuple[list[dict[str, object]], int]:
    first_html = fetch_text(base_url)
    total_pages = parse_total_pages(first_html)
    target_pages = total_pages if pages <= 0 else max(1, min(pages, total_pages))

    seen_urls: set[str] = set()
    all_items: list[dict[str, object]] = []
    for page in range(1, target_pages + 1):
        html_text = first_html if page == 1 else fetch_text(page_url(base_url, page))
        page_items = parse_products(html_text)
        for item in page_items:
            url = str(item.get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_items.append({**item, "source_page": page})
    return all_items, target_pages


def sort_products(items: list[dict[str, object]]) -> list[dict[str, object]]:
    def key(item: dict[str, object]) -> tuple[str, str]:
        release_date = str(item.get("release_date") or "")
        title = str(item.get("title") or "")
        return (release_date or "9999-12-31", title.lower())

    return sorted(items, key=key)


def annotate_products(items: list[dict[str, object]]) -> list[dict[str, object]]:
    today = date.today()
    out: list[dict[str, object]] = []
    for item in items:
        release_date = str(item.get("release_date") or "").strip()
        released = False
        if release_date:
            try:
                released = datetime.strptime(release_date, "%Y-%m-%d").date() <= today
            except ValueError:
                released = False
        out.append({**item, "is_released": released})
    return out


def sync_to_docs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATA_DIR.glob("*"):
        if path.is_file():
            shutil.copy2(path, DOCS_DIR / path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape ONE PIECE official products list.")
    parser.add_argument("--hard", action="store_true", help="Remove existing products output before scraping.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    parser.add_argument("--max-pages", type=int, default=0, help="Alias for --pages.")
    parser.add_argument("--pages", type=int, default=0, help="How many pages to scrape. Default: all pages.")
    args = parser.parse_args()

    if args.hard and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    pages = args.pages if args.pages > 0 else args.max_pages
    raw_items, pages_used = scrape_pages(PRODUCTS_URL, pages=pages)
    items = annotate_products(sort_products(raw_items))

    payload = {
        "source": PRODUCTS_URL,
        "scraped_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pages_scraped": pages_used,
        "items": items,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    sync_to_docs()
    print(f"Wrote {len(items)} One Piece product(s) from {pages_used} page(s) to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "one_piece"
OUTPUT_FILE = DATA_DIR / "products.json"
IMAGE_DIR = DATA_DIR / "product_images"


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
    block_pattern = re.compile(r'(?s)<li class="linkListColBox"[^>]*data-cat="([^"]+)"[^>]*>(.*?)</li>')
    for match in block_pattern.finditer(html_text):
        category_raw = strip_html(match.group(1))
        block = match.group(2)

        url_match = re.search(r'<a href="([^"]+)" class="linkListColItem">', block)
        title_match = re.search(r'<h4 class="linkListColTitle">(.*?)</h4>', block, flags=re.S)
        date_match = re.search(
            r'<p class="linkListColDate"><span class="head">(.*?)</span><time class="newsDate"(?: datetime="([^"]*)")?>(.*?)</time></p>',
            block,
            flags=re.S,
        )
        image_match = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', block)

        url = strip_html(url_match.group(1)) if url_match else ""
        title = strip_html(title_match.group(1)) if title_match else ""
        date_label = strip_html(date_match.group(1)) if date_match else ""
        date_iso = strip_html(date_match.group(2)) if date_match else ""
        date_text = strip_html(date_match.group(3)) if date_match else ""
        image_url = strip_html(image_match.group(1)) if image_match else ""
        if not title:
            continue
        if url.startswith("/"):
            url = f"https://en.onepiece-cardgame.com{url}"
        if image_url.startswith("/"):
            image_url = f"https://en.onepiece-cardgame.com{image_url}"

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
                "image_url": image_url,
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


def _image_extension(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if path.endswith(ext):
            return ext.replace(".jpeg", ".jpg")
    return ".webp"


def _stable_image_filename(item: dict[str, object], image_url: str) -> str:
    product_path = urllib.parse.urlparse(str(item.get("url") or "")).path
    product_slug = re.sub(r"[^a-z0-9]+", "-", (Path(product_path).stem or "product").lower()).strip("-") or "product"
    image_path = urllib.parse.urlparse(image_url).path
    image_stem = re.sub(r"[^a-z0-9]+", "-", (Path(image_path).stem or "image").lower()).strip("-") or "image"
    return f"{product_slug}_{image_stem}{_image_extension(image_url)}"


def cache_images_locally(items: list[dict[str, object]]) -> list[dict[str, object]]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, object]] = []
    for item in items:
        image_url = str(item.get("image_url") or "").strip()
        local_url = ""
        if image_url:
            try:
                file_name = _stable_image_filename(item, image_url)
                file_path = IMAGE_DIR / file_name
                if not file_path.exists():
                    print(f"[images] downloading {file_name}", flush=True)
                    req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=40) as response:
                        file_path.write_bytes(response.read())
                else:
                    print(f"[images] cached {file_name}", flush=True)
                local_url = f"./data/one_piece/product_images/{file_name}"
            except Exception:
                print(f"[images] failed: {str(item.get('title') or '').strip()}", flush=True)
        out.append({**item, "image_local_url": local_url})
    return out


def load_existing_items() -> list[dict[str, object]]:
    if not OUTPUT_FILE.exists():
        return []
    try:
        payload = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = payload.get("items")
    return items if isinstance(items, list) else []


def merge_new_items(
    existing_items: list[dict[str, object]],
    incoming_items: list[dict[str, object]],
    scraped_at_iso: str,
) -> list[dict[str, object]]:
    seen_urls: set[str] = set()
    merged: list[dict[str, object]] = []
    for item in existing_items:
        url = str(item.get("url") or "").strip()
        if url:
            seen_urls.add(url)
        merged.append(item)

    for item in incoming_items:
        url = str(item.get("url") or "").strip()
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        merged.append({**item, "added_at": scraped_at_iso})
    return merged


def page_url(base_url: str, page: int) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    rebuilt = parsed._replace(query=urllib.parse.urlencode(query))
    return urllib.parse.urlunparse(rebuilt)


def scrape_pages(base_url: str, pages: int = 0) -> tuple[list[dict[str, object]], int]:
    print(f"[scrape] fetching page 1: {base_url}", flush=True)
    first_html = fetch_text(base_url)
    total_pages = parse_total_pages(first_html)
    target_pages = total_pages if pages <= 0 else max(1, min(pages, total_pages))
    print(f"[scrape] total pages on site: {total_pages}", flush=True)
    print(f"[scrape] pages requested: {target_pages}", flush=True)

    seen_urls: set[str] = set()
    all_items: list[dict[str, object]] = []
    for page in range(1, target_pages + 1):
        print(f"[scrape] parsing page {page}/{target_pages}", flush=True)
        html_text = first_html if page == 1 else fetch_text(page_url(base_url, page))
        page_items = parse_products(html_text)
        print(f"[scrape] page {page} raw items: {len(page_items)}", flush=True)
        for item in page_items:
            url = str(item.get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_items.append({**item, "source_page": page})
    print(f"[scrape] deduped items from requested pages: {len(all_items)}", flush=True)
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



def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape ONE PIECE official products list.")
    parser.add_argument("--hard", action="store_true", help="Remove existing products output before scraping.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; ignored.")
    parser.add_argument("--max-pages", type=int, default=0, help="Alias for --pages.")
    parser.add_argument("--pages", type=int, default=0, help="How many pages to scrape. Default: all pages.")
    args = parser.parse_args()

    if args.hard and OUTPUT_FILE.exists():
        print(f"[startup] --hard enabled, removing existing file: {OUTPUT_FILE}", flush=True)
        OUTPUT_FILE.unlink()
    if args.hard and IMAGE_DIR.exists():
        print(f"[startup] --hard enabled, removing cached images: {IMAGE_DIR}", flush=True)
        shutil.rmtree(IMAGE_DIR, ignore_errors=True)

    pages = args.pages if args.pages > 0 else args.max_pages
    raw_items, pages_used = scrape_pages(PRODUCTS_URL, pages=pages)
    scraped_at_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    existing_items = [] if args.hard else load_existing_items()
    print(f"[existing] loaded existing items: {len(existing_items)}", flush=True)
    existing_urls = {
        str(item.get("url") or "").strip()
        for item in existing_items
        if str(item.get("url") or "").strip()
    }
    print(f"[existing] unique existing urls: {len(existing_urls)}", flush=True)
    new_raw_items = [
        item for item in raw_items
        if str(item.get("url") or "").strip() and str(item.get("url") or "").strip() not in existing_urls
    ]
    print(f"[delta] new items found on scrape: {len(new_raw_items)}", flush=True)
    if new_raw_items:
        for item in new_raw_items:
            print(f"[delta] + {str(item.get('title') or '').strip()}", flush=True)
    else:
        print("[delta] no new products; nothing to append", flush=True)
    incoming_items = annotate_products(sort_products(cache_images_locally(new_raw_items)))
    items = annotate_products(sort_products(merge_new_items(existing_items, incoming_items, scraped_at_iso)))

    payload = {
        "source": PRODUCTS_URL,
        "scraped_at": scraped_at_iso,
        "pages_scraped": pages_used,
        "items": items,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[write] writing merged payload -> {OUTPUT_FILE}", flush=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Wrote {len(items)} One Piece product(s) total "
        f"(added {len(incoming_items)} new) from {pages_used} page(s) to {OUTPUT_FILE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

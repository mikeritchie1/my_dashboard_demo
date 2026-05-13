from __future__ import annotations

import csv
import html
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


ONE_PIECE_DIR = Path(__file__).resolve().parent
WORKBOOK = ONE_PIECE_DIR / "One Piece Cards.xlsx"
ONE_PIECE_DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "one_piece"
REPO_DIR = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"

KNIGHTLY_COLLECTION_URL = env_get("SCRAPE_OP_KNIGHTLY_COLLECTION_URL", "https://www.knightlygaming.co.za/collections/one-piece-singles")
KNIGHTLY_PRODUCTS_URL = KNIGHTLY_COLLECTION_URL + "/products.json?limit=250&page={page}"

MARVELLOUS_COLLECTION_URL = env_get("SCRAPE_OP_MARVELLOUS_COLLECTION_URL", "https://marvelloushobbies.com/one-piece-singles/")
MARVELLOUS_PRODUCTS_URL = (
    env_get("SCRAPE_OP_MARVELLOUS_PRODUCTS_URL_TEMPLATE", "https://marvelloushobbies.com/wp-json/wc/store/v1/products?per_page=100&page={page}&category_ids[]=36")
)

TANUKI_COLLECTION_URL = env_get("SCRAPE_OP_TANUKI_COLLECTION_URL", "https://tanukitrader.co.za/")
TANUKI_PRODUCTS_URL = (
    env_get("SCRAPE_OP_TANUKI_PRODUCTS_URL_TEMPLATE", "https://tanukitrader.co.za/wp-json/wc/store/v1/products?per_page=100&page={page}")
)

BIG_BANG_COLLECTION_URL = env_get("SCRAPE_OP_BIG_BANG_COLLECTION_URL", "https://bigbangshop.co.za/collections/one-piece-single-cards")
BIG_BANG_PRODUCTS_URL = BIG_BANG_COLLECTION_URL + "/products.json?limit=250&page={page}"

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

TAG_RE = re.compile(r"<[^>]+>")
DRIVE_FILE_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)")

RARITY_NAMES = [
    "Super Rare",
    "Secret Rare",
    "Uncommon",
    "Common",
    "Leader",
    "Rare",
    "DON!!",
]


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


def setting(name: str) -> str:
    return (env_get(name, "") or local_secret(name)).strip()


def drive_file_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = DRIVE_FILE_ID_RE.search(url)
    if match:
        return match.group(1)
    marker = "id="
    if marker in url:
        return url.split(marker, 1)[1].split("&", 1)[0].strip()
    return ""


def drive_download_url() -> str:
    workbook_drive_url = setting("SCRAPE_OP_MISSING_CARDS_DRIVE_URL")
    workbook_drive_file_id = setting("SCRAPE_OP_MISSING_CARDS_DRIVE_FILE_ID")

    if workbook_drive_url:
        if "export=download" in workbook_drive_url:
            return workbook_drive_url
        file_id = drive_file_id_from_url(workbook_drive_url)
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        return workbook_drive_url
    if workbook_drive_file_id:
        return f"https://drive.google.com/uc?export=download&id={workbook_drive_file_id}"
    return ""


def drive_download_candidates() -> list[str]:
    workbook_drive_url = setting("SCRAPE_OP_MISSING_CARDS_DRIVE_URL")
    workbook_drive_file_id = setting("SCRAPE_OP_MISSING_CARDS_DRIVE_FILE_ID")

    urls: list[str] = []
    if workbook_drive_url:
        urls.append(workbook_drive_url)
        if "docs.google.com/spreadsheets" in workbook_drive_url:
            file_id = drive_file_id_from_url(workbook_drive_url)
            if file_id:
                urls.append(f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx")
        converted = drive_download_url()
        if converted and converted not in urls:
            urls.append(converted)
    elif workbook_drive_file_id:
        urls.append(f"https://drive.google.com/uc?export=download&id={workbook_drive_file_id}")
        urls.append(f"https://docs.google.com/spreadsheets/d/{workbook_drive_file_id}/export?format=xlsx")

    # Keep order while removing duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def workbook_from_drive() -> Path | None:
    candidates = drive_download_candidates()
    if not candidates:
        return None

    errors: list[str] = []
    for url in candidates:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                content_type = str(response.headers.get("Content-Type", "")).lower()
                content = response.read()
        except urllib.error.HTTPError as error:
            errors.append(f"{url} -> HTTP {error.code}")
            continue
        except urllib.error.URLError as error:
            errors.append(f"{url} -> URL error: {error.reason}")
            continue

        if not content:
            errors.append(f"{url} -> empty response")
            continue

        # Drive permission/login pages return HTML, not a workbook.
        if "text/html" in content_type:
            errors.append(f"{url} -> returned HTML instead of .xlsx (check sharing/permissions)")
            continue
        if not content.startswith(b"PK"):
            errors.append(f"{url} -> response was not an .xlsx file")
            continue

        temp_dir = Path(tempfile.gettempdir()) / "one_piece_scraper"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_workbook = temp_dir / "missing_cards_from_drive.xlsx"
        temp_workbook.write_bytes(content)
        return temp_workbook

    details = "\n".join(f"- {entry}" for entry in errors) if errors else "- no download candidates generated"
    raise RuntimeError(
        "Failed to download missing-cards workbook from Google Drive.\n"
        "Make sure the file is shared with Viewer access and link access is enabled.\n"
        f"Tried:\n{details}"
    )


def resolve_workbook_path(local_workbook: Path = WORKBOOK) -> Path:
    drive_workbook = workbook_from_drive()
    if drive_workbook:
        print(f"Using missing-cards workbook from Google Drive: {drive_workbook}")
        return drive_workbook
    if not local_workbook.exists():
        raise FileNotFoundError(
            "Missing workbook. Set SCRAPE_OP_MISSING_CARDS_DRIVE_URL (or SCRAPE_OP_MISSING_CARDS_DRIVE_FILE_ID) "
            "in environment/secrets.env, or restore local file services/one_piece/One Piece Cards.xlsx"
        )
    print(f"Using missing-cards workbook from local file: {local_workbook}")
    return local_workbook


def column_number(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    number = 0
    for ch in letters:
        number = number * 26 + ord(ch.upper()) - 64
    return number


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_card_number(value: object) -> str | None:
    if value is None:
        return None

    text = clean_text(value).upper()
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("OP-", "OP").replace("ST-", "ST")
    text = text.replace("EB-", "EB").replace("PRB-", "PRB")

    match = re.search(r"\b(OP|ST|EB|PRB)(\d{1,2})-(\d{1,3})\b", text)
    if not match:
        return None

    prefix, set_number, card_number = match.groups()
    return f"{prefix}{int(set_number):02d}-{int(card_number):03d}"


def load_sheet_rows(path: Path, sheet_name: str) -> list[dict[int, str]]:
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", NS):
                shared_strings.append("".join(t.text or "" for t in item.findall(".//a:t", NS)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        target = None
        for sheet in workbook.findall("a:sheets/a:sheet", NS):
            if sheet.attrib["name"] == sheet_name:
                rel_id = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                target = targets[rel_id]
                break

        if target is None:
            raise ValueError(f"Could not find sheet named {sheet_name!r}")

        sheet_path = "xl/" + target if not target.startswith("/") else target[1:]
        root = ET.fromstring(archive.read(sheet_path))

        rows: list[dict[int, str]] = []
        for row in root.findall("a:sheetData/a:row", NS):
            values: dict[int, str] = {}
            for cell in row.findall("a:c", NS):
                value = cell.find("a:v", NS)
                if value is None:
                    continue
                cell_value = value.text or ""
                if cell.attrib.get("t") == "s":
                    cell_value = shared_strings[int(cell_value)]
                values[column_number(cell.attrib["r"])] = cell_value
            rows.append(values)
        return rows


def missing_card_numbers(workbook: Path = WORKBOOK) -> set[str]:
    workbook = resolve_workbook_path(workbook)
    missing: set[str] = set()
    for row in load_sheet_rows(workbook, "Missing"):
        for value in row.values():
            card_number = normalize_card_number(value)
            if card_number:
                missing.add(card_number)
    return missing


def print_found_listings(store: str, matches: list[dict[str, object]]) -> None:
    print(f"Found missing-card listings on {store}: {len(matches)}")
    if not matches:
        print("Found listings: (none)")
        return
    print("Found listings:")
    for row in sorted_matches(matches):
        print(
            f"{row.get('card_number', '')} | "
            f"R {float(row.get('price') or 0):.2f} | "
            f"{row.get('title', '')} | "
            f"{row.get('store', '')} | "
            f"{row.get('url', '')}"
        )


def fetch_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_woo_page(url: str) -> tuple[list[dict], int, int]:
    """Fetch a WooCommerce Store API page. Returns (products, total_items, total_pages)."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        total_items = int(response.headers.get("X-WP-Total") or 0)
        total_pages = int(response.headers.get("X-WP-TotalPages") or 0)
        data = json.loads(response.read().decode("utf-8"))
    products = data if isinstance(data, list) else []
    return products, total_items, total_pages


def body_field(body_html: str, label: str) -> str:
    pattern = re.compile(
        r"<td>\s*" + re.escape(label) + r":\s*</td>\s*<td>\s*(.*?)\s*</td>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(body_html or "")
    if not match:
        return ""
    return clean_text(match.group(1))


def sorted_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        matches,
        key=lambda item: (
            float(item["price"]),
            str(item["card_number"]),
            str(item["store"]),
            str(item["title"]),
        ),
    )


_LISTING_FIELDS = [
    "card_number", "price", "title", "rarity", "store",
    "set_name", "condition", "stock", "available_variants", "url", "image_url",
    "scraped_at",
]

COMBINED_JSON = ONE_PIECE_DATA_DIR / "missing_cards.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _listing_dict(match: dict[str, object]) -> dict[str, object]:
    return {field: match.get(field, "") for field in _LISTING_FIELDS}


def _listing_key(listing: dict[str, object]) -> str:
    return f"{listing.get('card_number', '')}|{listing.get('url', '')}"


def _apply_scraped_at(
    new_listings: list[dict[str, object]],
    old_listings: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Preserve scraped_at for existing listings; set now for new ones."""
    now = _now_iso()
    old_map = {_listing_key(r): str(r.get("scraped_at") or "") for r in old_listings}
    for listing in new_listings:
        listing["scraped_at"] = old_map.get(_listing_key(listing)) or now
    return new_listings


def _write_json(listings: list[dict[str, object]]) -> None:
    ONE_PIECE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"listings": [_listing_dict(m) for m in listings]}
    COMBINED_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote missing_cards.json ({len(listings)} listings)", flush=True)


def update_store_in_combined_json(store_name: str, matches: list[dict[str, object]]) -> None:
    """Replace this store's entries in missing_cards.json, keeping all other stores intact."""
    old_all: list[dict[str, object]] = []
    old_store: list[dict[str, object]] = []
    if COMBINED_JSON.exists():
        data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
        for r in data.get("listings", []):
            (old_store if r.get("store") == store_name else old_all).append(r)
    matches = _apply_scraped_at(list(matches), old_store)
    _write_json(sorted_matches(old_all + matches))


def write_combined_json(listings: list[dict[str, object]]) -> None:
    old_listings: list[dict[str, object]] = []
    if COMBINED_JSON.exists():
        data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
        old_listings = data.get("listings", [])
    listings = _apply_scraped_at(sorted_matches(listings), old_listings)
    _write_json(listings)


def fetch_knightly_products() -> list[dict]:
    products: list[dict] = []
    for page in range(1, 50):
        print(f"Knightly Gaming: fetching page {page}...", flush=True)
        data = fetch_json(KNIGHTLY_PRODUCTS_URL.format(page=page))
        page_products = data.get("products", [])
        print(f"Knightly Gaming: page {page} -> {len(page_products)} products", flush=True)
        if not page_products:
            break
        products.extend(page_products)
    print(f"Knightly Gaming: {len(products)} products total", flush=True)
    return products


def match_knightly(missing: set[str], products: list[dict]) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for product in products:
        body = product.get("body_html") or ""
        card_number = normalize_card_number(body_field(body, "Card Number"))
        if not card_number or card_number not in missing:
            continue

        available_variants = [
            variant for variant in product.get("variants", []) if variant.get("available")
        ]
        if not available_variants:
            continue

        cheapest = min(available_variants, key=lambda item: float(item.get("price") or 0))
        images = product.get("images") or []
        matches.append(
            {
                "store": "Knightly Gaming",
                "card_number": card_number,
                "title": product.get("title") or "",
                "set_name": body_field(body, "Set Name"),
                "rarity": body_field(body, "Rarity"),
                "condition": cheapest.get("title") or "",
                "stock": "In stock",
                "price": float(cheapest.get("price") or 0),
                "available_variants": "; ".join(
                    f"{variant.get('title')} R{float(variant.get('price') or 0):.2f}"
                    for variant in available_variants
                ),
                "url": f"{KNIGHTLY_COLLECTION_URL}/products/{product.get('handle', '')}",
                "image_url": str(images[0].get("src") or "") if images else "",
            }
        )
    return matches


def run_knightly() -> list[dict[str, object]]:
    missing = missing_card_numbers()
    products = fetch_knightly_products()
    matches = sorted_matches(match_knightly(missing, products))
    update_store_in_combined_json("Knightly Gaming", matches)
    print_store_summary("Knightly Gaming", missing, products, matches)
    print_found_listings("Knightly Gaming", matches)
    return matches


def fetch_big_bang_products() -> list[dict]:
    products: list[dict] = []
    for page in range(1, 50):
        print(f"Big Bang Shop: fetching page {page}...", flush=True)
        data = fetch_json(BIG_BANG_PRODUCTS_URL.format(page=page))
        page_products = data.get("products", [])
        print(f"Big Bang Shop: page {page} -> {len(page_products)} products", flush=True)
        if not page_products:
            break
        products.extend(page_products)
    print(f"Big Bang Shop: {len(products)} products total", flush=True)
    return products


def match_big_bang(missing: set[str], products: list[dict]) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for product in products:
        body = product.get("body_html") or ""
        card_number = normalize_card_number(body_field(body, "Card Number"))
        if not card_number or card_number not in missing:
            continue

        available_variants = [
            variant for variant in product.get("variants", []) if variant.get("available")
        ]
        if not available_variants:
            continue

        cheapest = min(available_variants, key=lambda item: float(item.get("price") or 0))
        images = product.get("images") or []
        matches.append(
            {
                "store": "Big Bang Shop",
                "card_number": card_number,
                "title": product.get("title") or "",
                "set_name": body_field(body, "Set Name"),
                "rarity": body_field(body, "Rarity"),
                "condition": cheapest.get("title") or "",
                "stock": "In stock",
                "price": float(cheapest.get("price") or 0),
                "available_variants": "; ".join(
                    f"{variant.get('title')} R{float(variant.get('price') or 0):.2f}"
                    for variant in available_variants
                ),
                "url": f"{BIG_BANG_COLLECTION_URL}/products/{product.get('handle', '')}",
                "image_url": str(images[0].get("src") or "") if images else "",
            }
        )
    return matches


def run_big_bang() -> list[dict[str, object]]:
    missing = missing_card_numbers()
    products = fetch_big_bang_products()
    matches = sorted_matches(match_big_bang(missing, products))
    update_store_in_combined_json("Big Bang Shop", matches)
    print_store_summary("Big Bang Shop", missing, products, matches)
    print_found_listings("Big Bang Shop", matches)
    return matches


def _discover_marvellous_category_id() -> str:
    """Discover the right category_id for One Piece singles by listing all categories."""
    # Try WooCommerce Store API categories (product_cat taxonomy)
    try:
        data = fetch_json("https://marvelloushobbies.com/wp-json/wc/store/v1/products/categories?per_page=100&_fields=id,name,slug,parent")
        if isinstance(data, list):
            print(f"Marvellous Hobbies: {len(data)} product categories found:", flush=True)
            match_id = ""
            for cat in sorted(data, key=lambda c: str(c.get("name") or "")):
                name = str(cat.get("name") or "").strip()
                slug = str(cat.get("slug") or "").strip()
                cat_id = cat.get("id")
                print(f"  [{cat_id}] {name!r} (slug={slug!r})", flush=True)
                if re.search(r"one.piece", name, re.IGNORECASE) or re.search(r"one.piece", slug, re.IGNORECASE):
                    match_id = str(cat_id or "")
            if match_id:
                print(f"Marvellous Hobbies: auto-matched One Piece category id={match_id}", flush=True)
                return match_id
            print("Marvellous Hobbies: no 'one piece' category found in product_cat taxonomy", flush=True)
    except Exception as error:
        print(f"Marvellous Hobbies: Store API categories failed: {error}", flush=True)

    # Try WordPress REST API universe taxonomy as fallback
    try:
        data = fetch_json("https://marvelloushobbies.com/wp-json/wp/v2/universe?slug=one-piece&_fields=id,slug,name")
        if isinstance(data, list) and data:
            term = data[0]
            print(f"Marvellous Hobbies: found universe taxonomy term {term.get('name')!r} id={term.get('id')} — but WooCommerce Store API cannot filter by custom taxonomies", flush=True)
    except Exception:
        pass

    return ""


def _marvellous_url_template() -> str:
    """Build a URL filtered to One Piece products, or fall back to full catalog."""
    cat_id = _discover_marvellous_category_id()
    if cat_id:
        base = "https://marvelloushobbies.com/wp-json/wc/store/v1/products"
        return f"{base}?per_page=100&page={{page}}&category_ids[]={cat_id}"
    print("Marvellous Hobbies: WARNING — no category filter found, fetching full catalog (slow)", flush=True)
    return "https://marvelloushobbies.com/wp-json/wc/store/v1/products?per_page=100&page={page}"


def fetch_marvellous_products() -> list[dict]:
    url_template = _marvellous_url_template()
    products: list[dict] = []
    total_pages = 0
    for page in range(1, 200):
        print(f"Marvellous Hobbies: fetching page {page}{f'/{total_pages}' if total_pages else ''}...", flush=True)
        page_products, total_items, total_pages = fetch_woo_page(url_template.format(page=page))
        print(f"Marvellous Hobbies: page {page}/{total_pages} -> {len(page_products)} products (total: {total_items})", flush=True)
        if not page_products:
            break
        products.extend(page_products)
        if total_pages and page >= total_pages:
            break
    print(f"Marvellous Hobbies: {len(products)} products total", flush=True)
    return products


def woo_price(product: dict) -> float:
    prices = product.get("prices") or {}
    minor_unit = int(prices.get("currency_minor_unit") or 2)
    return int(prices.get("price") or 0) / (10**minor_unit)


def woo_category_names(product: dict) -> list[str]:
    return [clean_text(category.get("name")) for category in product.get("categories", [])]


def category_rarity(product: dict) -> str:
    category_text = " ".join(woo_category_names(product))
    for rarity in RARITY_NAMES:
        if re.search(r"\b" + re.escape(rarity) + r"\b", category_text, re.IGNORECASE):
            return rarity
    return ""


def category_set_name(product: dict) -> str:
    for name in woo_category_names(product):
        if re.search(r"\((OP|ST|EB|PRB)\d{1,2}\)", name, re.IGNORECASE):
            return name
    return ""


def match_marvellous(missing: set[str], products: list[dict]) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for product in products:
        permalink = str(product.get("permalink") or "").lower()
        if "one-piece" not in permalink and "one_piece" not in permalink:
            continue
        search_text = " ".join(
            str(product.get(key) or "")
            for key in ["name", "sku", "description", "short_description", "permalink"]
        )
        card_number = normalize_card_number(search_text)
        if not card_number or card_number not in missing:
            continue
        if not product.get("is_in_stock") or not product.get("is_purchasable"):
            continue

        stock = clean_text((product.get("stock_availability") or {}).get("text"))
        images = product.get("images") or []
        matches.append(
            {
                "store": "Marvellous Hobbies",
                "card_number": card_number,
                "title": clean_text(product.get("name")),
                "set_name": "",
                "rarity": "",
                "condition": "",
                "stock": stock,
                "price": woo_price(product),
                "available_variants": stock,
                "url": product.get("permalink") or MARVELLOUS_COLLECTION_URL,
                "image_url": str(images[0].get("src") or "") if images else "",
            }
        )
    return matches


def run_marvellous() -> list[dict[str, object]]:
    missing = missing_card_numbers()
    products = fetch_marvellous_products()
    matches = sorted_matches(match_marvellous(missing, products))
    update_store_in_combined_json("Marvellous Hobbies", matches)
    print_store_summary("Marvellous Hobbies", missing, products, matches)
    print_found_listings("Marvellous Hobbies", matches)
    return matches


def fetch_tanuki_products() -> list[dict]:
    products: list[dict] = []
    for page in range(1, 100):
        print(f"Tanuki Trader: fetching page {page}...", flush=True)
        page_products = fetch_json(TANUKI_PRODUCTS_URL.format(page=page))
        count = len(page_products) if isinstance(page_products, list) else 0
        print(f"Tanuki Trader: page {page} -> {count} products", flush=True)
        if not page_products:
            break
        products.extend(page_products)
    print(f"Tanuki Trader: {len(products)} products total", flush=True)
    return products


def match_tanuki(missing: set[str], products: list[dict]) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for product in products:
        search_text = " ".join(
            str(product.get(key) or "")
            for key in ["sku", "name", "description", "short_description", "permalink"]
        )
        card_number = normalize_card_number(search_text)
        if not card_number or card_number not in missing:
            continue
        if not product.get("is_in_stock") or not product.get("is_purchasable"):
            continue

        stock = clean_text((product.get("stock_availability") or {}).get("text"))
        images = product.get("images") or []
        matches.append(
            {
                "store": "Tanuki Trader",
                "card_number": card_number,
                "title": clean_text(product.get("name")),
                "set_name": category_set_name(product),
                "rarity": category_rarity(product),
                "condition": "",
                "stock": stock,
                "price": woo_price(product),
                "available_variants": stock,
                "url": product.get("permalink") or TANUKI_COLLECTION_URL,
                "image_url": str(images[0].get("src") or "") if images else "",
            }
        )
    return matches


def run_tanuki() -> list[dict[str, object]]:
    missing = missing_card_numbers()
    products = fetch_tanuki_products()
    matches = sorted_matches(match_tanuki(missing, products))
    update_store_in_combined_json("Tanuki Trader", matches)
    print_store_summary("Tanuki Trader", missing, products, matches)
    print_found_listings("Tanuki Trader", matches)
    return matches


def run_all() -> list[dict[str, object]]:
    missing = missing_card_numbers()
    failures: list[str] = []

    def scrape_store(
        store: str,
        fetcher,
        matcher,
    ) -> tuple[list[dict], list[dict[str, object]]]:
        try:
            products = fetcher()
            matches = sorted_matches(matcher(missing, products))
        except Exception as error:
            failures.append(f"{store}: {error}")
            print(f"{store} scrape failed: {error}", file=sys.stderr)
            return [], []
        return products, matches

    knightly_products, knightly_matches = scrape_store(
        "Knightly Gaming",
        fetch_knightly_products,
        match_knightly,
    )
    big_bang_products, big_bang_matches = scrape_store(
        "Big Bang Shop",
        fetch_big_bang_products,
        match_big_bang,
    )
    marvellous_products, marvellous_matches = scrape_store(
        "Marvellous Hobbies",
        fetch_marvellous_products,
        match_marvellous,
    )
    tanuki_products, tanuki_matches = scrape_store(
        "Tanuki Trader",
        fetch_tanuki_products,
        match_tanuki,
    )

    combined = sorted_matches(
        knightly_matches + big_bang_matches + marvellous_matches + tanuki_matches
    )
    write_combined_json(combined)

    print(f"Missing card numbers in spreadsheet: {len(missing)}")
    print(f"Knightly products fetched: {len(knightly_products)}")
    print(f"Knightly available missing listings: {len(knightly_matches)}")
    print(f"Big Bang products fetched: {len(big_bang_products)}")
    print(f"Big Bang available missing listings: {len(big_bang_matches)}")
    print(f"Marvellous products fetched: {len(marvellous_products)}")
    print(f"Marvellous available missing listings: {len(marvellous_matches)}")
    print(f"Tanuki products fetched: {len(tanuki_products)}")
    print(f"Tanuki available missing listings: {len(tanuki_matches)}")
    if failures:
        print("Store scrape failures:")
        for failure in failures:
            print(f"- {failure}")
    print_match_summary("Combined", combined)
    print_found_listings("Combined", combined)
    return combined


def print_store_summary(
    store: str,
    missing: set[str],
    products: list[dict],
    matches: list[dict[str, object]],
) -> None:
    print(f"Missing card numbers in spreadsheet: {len(missing)}")
    print(f"{store} products fetched: {len(products)}")
    print_match_summary(store, matches)


def print_match_summary(store: str, matches: list[dict[str, object]]) -> None:
    print(f"{store} available missing listings: {len(matches)}")
    print(f"{store} distinct missing card numbers available: {len({m['card_number'] for m in matches})}")
    print(f"{store} listing total: R {sum(float(m['price']) for m in matches):.2f}")

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_DIR))

from services.one_piece.scrape_products import PRODUCTS_URL, scrape_pages, sort_products


def main() -> int:
    parser = argparse.ArgumentParser(description="Test scrape for One Piece products.")
    parser.add_argument("--pages", type=int, default=0, help="How many pages to scrape. Default: all pages.")
    parser.add_argument("--details", action="store_true", help="Print extra details for each product.")
    args = parser.parse_args()

    items, pages_used = scrape_pages(PRODUCTS_URL, pages=args.pages)
    by_page: dict[int, list[dict[str, object]]] = {}
    for item in items:
        page = int(item.get("source_page") or 0)
        by_page.setdefault(page, []).append(item)

    total = 0
    for page in sorted(by_page):
        page_items = sort_products(by_page[page])
        print("")
        print(f"=== Page {page} ({len(page_items)} products) ===")
        for index, item in enumerate(page_items, start=1):
            name = str(item.get("title") or "").strip()
            release_date = str(item.get("release_date") or "").strip()
            date_text = str(item.get("release_date_text") or "").strip()
            product_type = str(item.get("category_label") or "").strip() or str(item.get("category") or "").strip()
            date_value = release_date or date_text or "Date TBA"
            print(f"{index:02d}. {name}")
            print(f"    Date: {date_value}")
            print(f"    Type: {product_type}")
            if args.details:
                print(f"    Label: {str(item.get('date_label') or '').strip() or '-'}")
                print(f"    URL: {str(item.get('url') or '').strip() or '-'}")
            total += 1

    print("")
    print("=== Summary ===")
    print(f"Pages scraped: {pages_used}")
    print(f"Total products found: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_DIR / "data" / "one_piece"
DOCS_DIR = REPO_DIR / "docs" / "data" / "one_piece"


def sync_outputs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATA_DIR.iterdir():
        target = DOCS_DIR / path.name
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        elif path.is_file():
            shutil.copy2(path, target)
    print(f"Synced One Piece data to dashboard: {DOCS_DIR}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run One Piece missing-card scrapes.")
    parser.add_argument("--source", choices=["all", "bigbang", "knightly", "marvellous", "tanuki"], default="all", help="Which store source to scrape.")
    parser.add_argument("--hard", action="store_true", help="Remove selected report outputs before scraping.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for wrapper consistency; store scraping is not item-limited.")
    parser.add_argument("--max-pages", type=int, default=0, help="Accepted for wrapper consistency; store pagination is source-defined.")
    args = parser.parse_args()

    if args.hard:
        patterns = ["*_missing_available.csv", "new_missing_cards.json"] if args.source == "all" else [f"*{args.source}*_missing_available.csv"]
        for pattern in patterns:
            for path in DATA_DIR.glob(pattern):
                print(f"Removing stale One Piece output: {path}", flush=True)
                path.unlink()

    command = [sys.executable, "services/one_piece/find_missing_cards.py", args.source]
    print(f"Running One Piece scrape: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=REPO_DIR, check=True)
    product_command = [sys.executable, "services/one_piece/scrape_products.py", "--pages", "1"]
    if args.hard:
        product_command.append("--hard")
    print(f"Running One Piece products scrape: {' '.join(product_command)}", flush=True)
    subprocess.run(product_command, cwd=REPO_DIR, check=True)
    sync_outputs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

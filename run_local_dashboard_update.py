from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent
DATA_DIR = REPO_DIR / "data"

TASKS = {
    "cards": [[sys.executable, "services/one_piece/notify_new_cards.py", "--store", "all", "--mode", "all", "--no-email"]],
    "specials": [[sys.executable, "services/events/scrape_specials.py"]],
    "events": [
        [sys.executable, "services/events/scrape_quicket_events.py"],
        [sys.executable, "services/events/scrape_webtickets_events.py"],
        [sys.executable, "services/events/scrape_google_calendar.py"],
    ],
    "releases": [[sys.executable, "services/release_radar/scrape_releases.py"]],
    "coming-soon": [[sys.executable, "services/release_radar/scrape_coming_soon.py"]],
    "media": [[sys.executable, "services/media/scrape_watchlist.py"]],
    "watchlist": [[sys.executable, "services/media/scrape_watchlist.py"]],
}


def run_commands(task: str) -> None:
    if task == "all":
        commands = [command for commands in TASKS.values() for command in commands]
    else:
        commands = TASKS[task]

    for command in commands:
        subprocess.run(command, cwd=REPO_DIR, check=True)


def write_metadata() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = DATA_DIR / "metadata.json"
    metadata = {"last_scraped_at": datetime.now(timezone.utc).isoformat()}
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local scrapers and update central data/")
    parser.add_argument(
        "task",
        nargs="?",
        choices=["all", *TASKS.keys()],
        default="all",
        help="Which scraper set to run.",
    )
    args = parser.parse_args()

    run_commands(args.task)
    write_metadata()
    print(f"Updated data in {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

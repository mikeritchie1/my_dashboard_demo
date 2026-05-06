from __future__ import annotations

import argparse
import shutil
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent
DATA_DIR = REPO_DIR / "data"

TASKS = {
    "cards": [[sys.executable, "services/one_piece/find_missing_cards.py", "all"]],
    "specials": [[sys.executable, "services/events/scrape_specials.py"]],
    "events": [
        [sys.executable, "services/events/scrape_bandsintown_events.py"],
        [sys.executable, "services/events/scrape_quicket_events.py"],
        [sys.executable, "services/events/scrape_webtickets_events.py"],
        [sys.executable, "services/events/scrape_google_calendar.py"],
    ],
    "releases": [[sys.executable, "services/release_radar/scrape_releases.py"]],
    "coming-soon": [[sys.executable, "services/release_radar/scrape_coming_soon.py"]],
    "game-releases": [[sys.executable, "services/release_radar/scrape_game_releases.py"]],
    "media": [[sys.executable, "services/media/scrape_watchlist.py", "--scope", "both"]],
    "watchlist": [[sys.executable, "services/media/scrape_watchlist.py", "--scope", "watchlist"]],
    "gamelist": [[sys.executable, "services/media/scrape_watchlist.py", "--scope", "games", "--type", "games"]],
    "digest": [[sys.executable, "services/daily_digest/send_daily_digest.py", "--no-email"]],
}


def run_commands(task: str) -> None:
    if task == "all":
        scheduled: list[tuple[str, list[str]]] = [
            (name, command)
            for name, commands in TASKS.items()
            if name != "digest"
            for command in commands
        ]
    else:
        scheduled = [(task, command) for command in TASKS[task]]

    total = len(scheduled)
    for index, (task_name, command) in enumerate(scheduled, start=1):
        command_text = " ".join(str(part) for part in command)
        print(f"[{index}/{total}] Running ({task_name}): {command_text}")
        subprocess.run(command, cwd=REPO_DIR, check=True)
        print(f"[{index}/{total}] Done ({task_name}): {command_text}")


def write_metadata() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = DATA_DIR / "metadata.json"
    metadata = {"last_scraped_at": datetime.now(timezone.utc).isoformat()}
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def sync_data_to_docs() -> None:
    docs_dir = REPO_DIR / "docs"
    if not docs_dir.exists():
        return
    target = docs_dir / "data"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DATA_DIR, target)


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
    sync_data_to_docs()
    print(f"Updated data in {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

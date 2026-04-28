from __future__ import annotations

import argparse
import csv
import os
import shutil
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path


CURRENT_REPORT = Path("all_stores_missing_available.csv")
PREVIOUS_REPORT = Path(".scrape/previous_all_stores_missing_available.csv")
MATCH_KEY = ("card_number", "store", "url")


def run_scraper() -> None:
    subprocess.run(
        [sys.executable, "find_missing_cards.py", "all"],
        check=True,
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def row_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple((row.get(field) or "").strip() for field in MATCH_KEY)


def new_rows(today: list[dict[str, str]], previous: list[dict[str, str]]) -> list[dict[str, str]]:
    previous_keys = {row_key(row) for row in previous}
    return [row for row in today if row_key(row) not in previous_keys]


def money(value: str) -> str:
    try:
        return f"R {float(value):.2f}"
    except (TypeError, ValueError):
        return value or ""


def card_line(row: dict[str, str]) -> str:
    pieces = [
        row.get("card_number", ""),
        money(row.get("price", "")),
        row.get("title", ""),
        row.get("rarity", ""),
        row.get("store", ""),
        row.get("stock", ""),
    ]
    summary = " | ".join(piece for piece in pieces if piece)
    url = row.get("url", "")
    return f"{summary}\n{url}" if url else summary


def email_body(rows: list[dict[str, str]]) -> str:
    lines = [
        f"New missing cards available: {len(rows)}",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {card_line(row)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def send_email(rows: list[dict[str, str]]) -> None:
    smtp_host = env_required("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = env_required("SMTP_USER")
    smtp_password = env_required("SMTP_PASSWORD")
    email_to = env_required("EMAIL_TO")
    email_from = os.environ.get("EMAIL_FROM", "").strip() or smtp_user

    message = EmailMessage()
    message["Subject"] = f"One Piece cards: {len(rows)} new available"
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(email_body(rows))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def update_snapshot() -> None:
    PREVIOUS_REPORT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CURRENT_REPORT, PREVIOUS_REPORT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Email new missing-card listings once per day.")
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Compare existing CSV files without running the scraper first.",
    )
    args = parser.parse_args()

    if not args.no_scrape:
        run_scraper()

    if not CURRENT_REPORT.exists():
        print(f"Could not find current report: {CURRENT_REPORT}", file=sys.stderr)
        return 2

    today = read_rows(CURRENT_REPORT)
    previous = read_rows(PREVIOUS_REPORT)

    if not previous:
        update_snapshot()
        print("No previous snapshot found. Saved today's report as the baseline.")
        return 0

    additions = new_rows(today, previous)
    if not additions:
        update_snapshot()
        print("No new cards found. Snapshot updated.")
        return 0

    send_email(additions)
    update_snapshot()
    print(f"Sent email for {len(additions)} new card listing(s). Snapshot updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

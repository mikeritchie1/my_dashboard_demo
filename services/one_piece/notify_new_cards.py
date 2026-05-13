from __future__ import annotations

import argparse
import json
import os
import shutil
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path


ONE_PIECE_DIR = Path(__file__).resolve().parent
ONE_PIECE_DATA_DIR = Path(__file__).resolve().parents[2] / "docs" / "data" / "one_piece"

STORE_NAMES = {
    "bigbang": "Big Bang Shop",
    "bigbangshop": "Big Bang Shop",
    "knightly": "Knightly Gaming",
    "knightlygaming": "Knightly Gaming",
    "marvellous": "Marvellous Hobbies",
    "marvelloushobbies": "Marvellous Hobbies",
    "tanuki": "Tanuki Trader",
    "tanukitrader": "Tanuki Trader",
}

COMBINED_JSON = ONE_PIECE_DATA_DIR / "missing_cards.json"
LATEST_REPORT = Path(".scrape/latest_new_cards.txt")
MATCH_KEY = ("card_number", "store", "url")
CHANGE_FIELDS = ("price", "stock", "condition", "available_variants")


def normalized_store(value: str) -> str:
    return value.lower().replace("-", "").replace("_", "")


def store_display_name(store: str) -> str:
    return STORE_NAMES.get(normalized_store(store), store)


def previous_snapshot_path(store: str, snapshot_scope: str = "") -> Path:
    scope = normalized_store(snapshot_scope)
    prefix = f"{scope}_" if scope else ""
    return Path(f".scrape/{prefix}previous_{normalized_store(store)}.json")


def run_scraper(store: str) -> None:
    subprocess.run(
        [sys.executable, str(ONE_PIECE_DIR / "find_missing_cards.py"), store],
        check=True,
    )


def read_rows(path: Path, store: str = "all") -> list[dict[str, str]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    listings = data.get("listings", [])
    if store != "all":
        name = store_display_name(store)
        listings = [r for r in listings if r.get("store", "") == name]
    return [{k: str(v) for k, v in row.items()} for row in listings]


def row_key(row: dict[str, str]) -> str:
    return "|".join((row.get(f) or "").strip() for f in MATCH_KEY)


def diff_rows(
    today: list[dict[str, str]],
    previous: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (additions, changes). Removals are ignored."""
    prev_map = {row_key(r): r for r in previous}
    additions: list[dict[str, str]] = []
    changes: list[dict[str, str]] = []
    for row in today:
        key = row_key(row)
        if key not in prev_map:
            additions.append(row)
        else:
            old = prev_map[key]
            if any(row.get(f) != old.get(f) for f in CHANGE_FIELDS):
                changes.append(row)
    return additions, changes


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
    summary = " | ".join(p for p in pieces if p)
    url = row.get("url", "")
    return f"{summary}\n{url}" if url else summary


def card_section(title: str, rows: list[dict[str, str]]) -> list[str]:
    lines = [f"{title}: {len(rows)}", ""]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {card_line(row)}")
        lines.append("")
    return lines


def build_email_body(
    store: str,
    additions: list[dict[str, str]],
    changes: list[dict[str, str]],
    window_label: str,
    include_all: list[dict[str, str]] | None = None,
) -> str:
    lines = [f"One Piece card update for {store}", ""]
    if additions:
        lines.extend(card_section(f"New {window_label}", additions))
    else:
        lines += [f"New {window_label}: 0", ""]
    if changes:
        lines.extend(card_section(f"Changed {window_label}", changes))
    if include_all is not None:
        lines.extend(card_section("All current listings", include_all))
    return "\n".join(lines).strip() + "\n"


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def write_latest_report(body: str, snapshot_scope: str) -> None:
    scope = normalized_store(snapshot_scope)
    path = Path(f".scrape/latest_{scope}_new_cards.txt") if scope else LATEST_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def send_email(subject: str, body: str) -> None:
    smtp_host = env_required("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = env_required("SMTP_USER")
    smtp_password = env_required("SMTP_PASSWORD")
    email_to = env_required("EMAIL_TO")
    email_from = os.environ.get("EMAIL_FROM", "").strip() or smtp_user

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def save_snapshot(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"listings": rows}, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Email new/changed missing-card listings since the last snapshot.")
    parser.add_argument("--no-scrape", action="store_true", help="Skip running the scraper first.")
    parser.add_argument("--store", default=os.environ.get("CARD_STORE", "all"),
                        help="Store to check: all, knightly, bigbang, marvellous, or tanuki.")
    parser.add_argument("--mode", choices=["new", "all"], default=os.environ.get("CARD_NOTIFY_MODE", "new"),
                        help="'new' emails only changes; 'all' also includes full current listing.")
    parser.add_argument("--no-email", action="store_true", help="Write report file without sending email.")
    parser.add_argument("--snapshot-scope", default=os.environ.get("CARD_NOTIFY_SNAPSHOT_SCOPE", ""),
                        help="Snapshot namespace, e.g. 'hourly' to keep separate baselines.")
    parser.add_argument("--window-label", default=os.environ.get("CARD_NOTIFY_WINDOW_LABEL", "since last email"),
                        help="Human-friendly label for the window, e.g. 'in the last hour'.")
    args = parser.parse_args()

    store = normalized_store(args.store)
    window_label = args.window_label.strip() or "since last email"
    snapshot = previous_snapshot_path(store, args.snapshot_scope)

    if not args.no_scrape:
        run_scraper(store)

    if not COMBINED_JSON.exists():
        print(f"Could not find {COMBINED_JSON}", file=sys.stderr)
        return 2

    today = read_rows(COMBINED_JSON, store)

    if not snapshot.exists():
        save_snapshot(snapshot, today)
        print(f"No previous snapshot for {store}. Saved baseline.")
        return 0

    previous = read_rows(snapshot, store)
    additions, changes = diff_rows(today, previous)

    include_all = today if args.mode == "all" else None
    body = build_email_body(store, additions, changes, window_label, include_all)
    write_latest_report(body, args.snapshot_scope)

    if not additions and not changes:
        save_snapshot(snapshot, today)
        print(f"No additions or changes {window_label} for {store}. Snapshot updated.")
        return 0

    subject = f"One Piece cards: {len(additions)} new, {len(changes)} changed ({store})"
    if not args.no_email:
        send_email(subject, body)
    save_snapshot(snapshot, today)
    action = "Prepared report" if args.no_email else "Sent email"
    print(f"{action}: {len(additions)} new, {len(changes)} changed for {store}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

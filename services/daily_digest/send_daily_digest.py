from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable


REPO_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_DIR / "data"
SNAPSHOT_DIR = REPO_DIR / ".scrape" / "daily_digest"
LATEST_DIGEST = REPO_DIR / ".scrape" / "latest_daily_digest.txt"

Item = dict[str, Any]


@dataclass(frozen=True)
class Section:
    title: str
    path: Path
    loader: Callable[[Path], list[Item]]
    key_fields: tuple[str, ...] = ("url", "title")
    fallback_previous: Path | None = None


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def load_json_items(*keys: str) -> Callable[[Path], list[Item]]:
    def loader(path: Path) -> list[Item]:
        payload = load_json(path)
        for key in keys:
            if not isinstance(payload, dict):
                return []
            payload = payload.get(key)
        return payload if isinstance(payload, list) else []

    return loader


def load_json_list(path: Path) -> list[Item]:
    payload = load_json(path)
    return payload if isinstance(payload, list) else []


def load_csv_rows(path: Path) -> list[Item]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def load_specials(path: Path) -> list[Item]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        return []

    items: list[Item] = []
    for group in payload.get("groups", []) or []:
        if not isinstance(group, dict):
            continue
        group_title = str(group.get("title") or "").strip()
        for item in group.get("items", []) or []:
            if isinstance(item, dict):
                items.append({**item, "group": group_title})

    for venue, location in (payload.get("locations") or {}).items():
        if isinstance(location, dict):
            items.append({**location, "title": location.get("title") or venue, "group": "Locations"})
    return items


SECTIONS = [
    Section(
        "One Piece Cards",
        DATA_DIR / "one_piece" / "all_stores_missing_available.csv",
        load_csv_rows,
        ("card_number", "store", "url"),
        REPO_DIR / ".scrape" / "previous_all_stores_missing_available.csv",
    ),
    Section("New Releases", DATA_DIR / "release_radar" / "pahe_latest.json", load_json_items("items")),
    Section("Coming Soon Movies", DATA_DIR / "release_radar" / "coming_soon.json", load_json_items("items")),
    Section("New Game Releases", DATA_DIR / "release_radar" / "game_releases.json", load_json_items("new_releases")),
    Section("Coming Soon Games", DATA_DIR / "release_radar" / "game_releases.json", load_json_items("coming_soon")),
    Section("Bandsintown Events", DATA_DIR / "events" / "bandsintown_events.json", load_json_list),
    Section("Quicket Events", DATA_DIR / "events" / "quicket_events.json", load_json_list),
    Section("Webtickets Events", DATA_DIR / "events" / "webtickets_wc_events.json", load_json_list),
    Section("Google Calendar", DATA_DIR / "events" / "google_calendar_events.json", load_json_items("items")),
    Section("Specials & Places", DATA_DIR / "events" / "specials.json", load_specials, ("group", "title", "venue")),
]


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def snapshot_path(section: Section) -> Path:
    safe_name = section.title.lower().replace("&", "and").replace(" ", "_")
    suffix = ".csv" if section.path.suffix.lower() == ".csv" else ".json"
    return SNAPSHOT_DIR / f"{safe_name}{suffix}"


def read_previous(section: Section) -> list[Item]:
    current_snapshot = snapshot_path(section)
    if current_snapshot.exists():
        return section.loader(current_snapshot)
    if section.fallback_previous and section.fallback_previous.exists():
        return section.loader(section.fallback_previous)
    return []


def has_previous_snapshot(section: Section) -> bool:
    current_snapshot = snapshot_path(section)
    if current_snapshot.exists():
        return True
    return bool(section.fallback_previous and section.fallback_previous.exists())


def normalized_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value or "").strip()


def item_key(item: Item, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = normalized_value(item.get(field))
        if value:
            return value
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def index_items(items: list[Item], fields: tuple[str, ...]) -> dict[str, Item]:
    indexed: dict[str, Item] = {}
    for item in items:
        indexed[item_key(item, fields)] = item
    return indexed


def changed_items(today: dict[str, Item], previous: dict[str, Item]) -> list[Item]:
    changed: list[Item] = []
    for key, item in today.items():
        if key in previous and item != previous[key]:
            changed.append(item)
    return changed


def compact_line(item: Item) -> str:
    title = normalized_value(item.get("title") or item.get("name") or item.get("card_number") or item.get("venue"))
    date = normalized_value(item.get("release_date") or item.get("start") or item.get("date") or item.get("date_text"))
    venue = normalized_value(item.get("venue") or item.get("store") or item.get("group"))
    price = normalized_value(item.get("price"))
    url = normalized_value(item.get("url"))
    pieces = [piece for piece in [title, date, venue, price] if piece]
    summary = " | ".join(pieces) if pieces else json.dumps(item, sort_keys=True, ensure_ascii=False)
    return f"{summary}\n{url}" if url else summary


def section_lines(title: str, label: str, items: list[Item], limit: int) -> list[str]:
    lines = [f"{label}: {len(items)}"]
    for index, item in enumerate(items[:limit], start=1):
        lines.append(f"{index}. {compact_line(item)}")
    if len(items) > limit:
        lines.append(f"...and {len(items) - limit} more")
    lines.append("")
    return lines


def build_digest(limit: int) -> tuple[str, int]:
    lines = ["Daily dashboard digest", ""]
    total_changes = 0

    for section in SECTIONS:
        today_items = section.loader(section.path)
        previous_items = read_previous(section)
        previous_exists = has_previous_snapshot(section)
        today = index_items(today_items, section.key_fields)
        previous = index_items(previous_items, section.key_fields)

        added = [today[key] for key in today.keys() - previous.keys()]
        removed = [previous[key] for key in previous.keys() - today.keys()]
        updated = changed_items(today, previous)

        lines.extend([section.title, "-" * len(section.title)])
        if previous_exists:
            total_changes += len(added) + len(removed) + len(updated)
            lines.extend(section_lines("Added", "Added", added, limit))
            lines.extend(section_lines("Updated", "Updated", updated, limit))
            lines.extend(section_lines("Removed", "Removed", removed, limit))
        else:
            lines.append(f"Baseline saved: {len(today_items)} current item(s).")
            lines.append("")

    return "\n".join(lines).strip() + "\n", total_changes


def update_snapshots() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for section in SECTIONS:
        if section.path.exists():
            shutil.copy2(section.path, snapshot_path(section))


def send_email(body: str, total_changes: int) -> None:
    smtp_host = env_required("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = env_required("SMTP_USER")
    smtp_password = env_required("SMTP_PASSWORD")
    email_to = env_required("EMAIL_TO")
    email_from = os.environ.get("EMAIL_FROM", "").strip() or smtp_user

    message = EmailMessage()
    message["Subject"] = f"Dashboard daily digest: {total_changes} change(s)"
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Email daily dashboard changes across scraper sections.")
    parser.add_argument("--no-email", action="store_true", help="Write digest and snapshots without sending email.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum changed items to list per change type.")
    args = parser.parse_args()

    body, total_changes = build_digest(max(1, args.limit))
    LATEST_DIGEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST_DIGEST.write_text(body, encoding="utf-8")
    if not args.no_email:
        send_email(body, total_changes)
    update_snapshots()
    action = "Prepared" if args.no_email else "Sent"
    print(f"{action} daily digest with {total_changes} change(s). Snapshots updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

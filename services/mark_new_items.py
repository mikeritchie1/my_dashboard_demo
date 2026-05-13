from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_DIR / "docs" / "data"
SNAPSHOT_DIR = REPO_DIR / ".scrape" / "previous_data"


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def stable_key(item: Any, fields: list[str]) -> str:
    if not isinstance(item, dict):
        return ""
    parts: list[str] = []
    for field in fields:
        value = str(item.get(field, "")).strip().lower()
        if not value:
            return ""
        parts.append(value)
    return "|".join(parts)


def apply_list_markers(
    current_list: Any,
    previous_list: Any,
    key_fields: list[str],
    skip_when: list[tuple[str, str]] | None = None,
) -> int:
    if not isinstance(current_list, list):
        return 0
    previous_items = previous_list if isinstance(previous_list, list) else []
    has_previous_snapshot = isinstance(previous_list, list)
    previous_keys = {
        stable_key(item, key_fields)
        for item in previous_items
        if stable_key(item, key_fields)
    }
    marked = 0
    for item in current_list:
        if not isinstance(item, dict):
            continue
        if skip_when and any(str(item.get(k, "")).strip().lower() == v for k, v in skip_when):
            item["is_new"] = False
            continue
        if not has_previous_snapshot:
            item["is_new"] = False
            continue
        key = stable_key(item, key_fields)
        is_new = bool(key) and key not in previous_keys
        item["is_new"] = is_new
        if is_new:
            marked += 1
    return marked


def get_path(payload: Any, dotted: str) -> Any:
    node = payload
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def process_file(path_str: str, targets: list[dict[str, Any]]) -> int:
    current_path = DATA_DIR / path_str
    previous_path = SNAPSHOT_DIR / path_str
    current_payload = load_json(current_path)
    previous_payload = load_json(previous_path)
    if current_payload is None:
        return 0

    total_marked = 0
    for target in targets:
        key_fields = target["key_fields"]
        skip_when = target.get("skip_when")
        path = target.get("path")
        if path:
            current_list = get_path(current_payload, path)
            previous_list = get_path(previous_payload, path) if previous_payload is not None else None
        else:
            current_list = current_payload
            previous_list = previous_payload
        total_marked += apply_list_markers(current_list, previous_list, key_fields, skip_when=skip_when)

    write_json(current_path, current_payload)
    return total_marked


def main() -> int:
    rules: dict[str, list[dict[str, Any]]] = {
        "release_radar/pahe_latest.json": [{"path": "items", "key_fields": ["url", "title"]}],
        "release_radar/coming_soon.json": [{"path": "items", "key_fields": ["url", "title"]}],
        "release_radar/imax_waterfront.json": [{"path": "items", "key_fields": ["url", "title"]}],
        "release_radar/galileo_movies.json": [{"path": "items", "key_fields": ["url", "title"]}],
        "release_radar/game_releases.json": [
            {"path": "new_releases", "key_fields": ["url", "title"]},
            {"path": "coming_soon", "key_fields": ["url", "title"]},
        ],
        "news/news.json": [
            {"path": "top_items", "key_fields": ["id", "url"]},
            {"path": "items", "key_fields": ["id", "url"], "skip_when": [("is_pinned_module", "true")]},
        ],
        "events/quicket_events.json": [{"key_fields": ["url", "start", "title"]}],
        "events/bandsintown_events.json": [{"key_fields": ["url", "start", "title"]}],
        "events/webtickets_wc_events.json": [{"key_fields": ["url", "start", "title"]}],
        "events/google_calendar_events.json": [{"path": "items", "key_fields": ["url", "start", "title"]}],
        "media/watchlist.json": [
            {"path": "currently_watching.movies", "key_fields": ["title"]},
            {"path": "currently_watching.series", "key_fields": ["title"]},
            {"path": "currently_watching.anime_movies", "key_fields": ["title"]},
            {"path": "currently_watching.anime_series", "key_fields": ["title"]},
            {"path": "backlog.movies", "key_fields": ["title"]},
            {"path": "backlog.series", "key_fields": ["title"]},
            {"path": "backlog.anime_movies", "key_fields": ["title"]},
            {"path": "backlog.anime_series", "key_fields": ["title"]},
            {"path": "history_by_year", "key_fields": []},
        ],
        "media/gameslist.json": [
            {"path": "currently_watching.games.aaa", "key_fields": ["title"]},
            {"path": "currently_watching.games.indie", "key_fields": ["title"]},
            {"path": "currently_watching.games.coop", "key_fields": ["title"]},
            {"path": "currently_watching.games.couch_coop", "key_fields": ["title"]},
            {"path": "currently_watching.games.lan", "key_fields": ["title"]},
            {"path": "backlog.game_aaa", "key_fields": ["title"]},
            {"path": "backlog.game_indie", "key_fields": ["title"]},
            {"path": "backlog.game_coop", "key_fields": ["title"]},
            {"path": "backlog.game_couch_coop", "key_fields": ["title"]},
        ],
    }

    # Special handling for nested history arrays in media payloads.
    for media_file in ("media/watchlist.json", "media/gameslist.json"):
        current_path = DATA_DIR / media_file
        previous_path = SNAPSHOT_DIR / media_file
        current_payload = load_json(current_path)
        previous_payload = load_json(previous_path)
        if isinstance(current_payload, dict):
            prev_by_year: dict[str, set[str]] = {}
            has_previous_snapshot = isinstance(previous_payload, dict)
            for group in previous_payload.get("history_by_year", []) if isinstance(previous_payload, dict) else []:
                if not isinstance(group, dict):
                    continue
                year = str(group.get("year", "")).strip()
                entries = group.get("entries", [])
                if not year or not isinstance(entries, list):
                    continue
                prev_by_year[year] = {
                    stable_key(entry, ["type", "title"]) for entry in entries if stable_key(entry, ["type", "title"])
                }
            for group in current_payload.get("history_by_year", []):
                if not isinstance(group, dict):
                    continue
                year = str(group.get("year", "")).strip()
                entries = group.get("entries", [])
                if not year or not isinstance(entries, list):
                    continue
                year_keys = prev_by_year.get(year, set())
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    key = stable_key(entry, ["type", "title"])
                    entry["is_new"] = bool(key) and has_previous_snapshot and key not in year_keys
            write_json(current_path, current_payload)

    marked_counts: dict[str, int] = {}
    for file_path, targets in rules.items():
        marked = process_file(file_path, [t for t in targets if t.get("path") != "history_by_year"])
        marked_counts[file_path] = marked

    total = sum(marked_counts.values())
    print(f"Marked {total} new item(s) across {len(marked_counts)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

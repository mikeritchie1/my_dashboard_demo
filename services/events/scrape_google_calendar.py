from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get


REPO_DIR = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_FILE = REPO_DIR / "secrets.env"
OUTPUT_DIR = REPO_DIR / "data" / "events"
OUTPUT_FILE = OUTPUT_DIR / "google_calendar_events.json"
LOCAL_TZ = timezone(timedelta(hours=2), "SAST")
GOOGLE_CALENDAR_API_BASE_URL = env_get("SCRAPE_GOOGLE_CALENDAR_API_BASE_URL", "https://www.googleapis.com/calendar/v3")


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


def secret(name: str) -> str:
    return env_get(name, "") or local_secret(name)


def read_calendar_ids() -> list[str]:
    raw = secret("GOOGLE_CALENDAR_IDS")
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def fetch_calendar_events(calendar_id: str, api_key: str, start: datetime, end: datetime) -> list[dict]:
    encoded_id = urllib.parse.quote(calendar_id, safe="")
    params = urllib.parse.urlencode(
        {
            "key": api_key,
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": start.isoformat().replace("+00:00", "Z"),
            "timeMax": end.isoformat().replace("+00:00", "Z"),
            "maxResults": "250",
        }
    )
    url = f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/{encoded_id}/events?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "my-dashboard/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("items", [])


def date_key_from_start(start_obj: dict) -> str:
    value = start_obj.get("dateTime") or start_obj.get("date", "")
    if "T" in value:
        return value.split("T", 1)[0]
    return value


def classify_event(summary: str) -> str:
    label = (summary or "").lower()
    if "birthday" in label or "bday" in label:
        return "birthday"
    return "calendar"


def scrape() -> dict:
    api_key = secret("GOOGLE_API_KEY")
    calendar_ids = read_calendar_ids()
    if not api_key:
        return {"error": "Missing GOOGLE_API_KEY", "items": []}
    if not calendar_ids:
        return {"error": "Missing GOOGLE_CALENDAR_IDS", "items": []}

    now_utc = datetime.now(timezone.utc)
    window_end = now_utc + timedelta(days=31)
    out_items: list[dict] = []

    for calendar_id in calendar_ids:
        try:
            events = fetch_calendar_events(calendar_id, api_key, now_utc, window_end)
        except Exception as exc:  # noqa: BLE001
            out_items.append(
                {
                    "source_calendar_id": calendar_id,
                    "type": "error",
                    "title": f"Failed to load calendar: {calendar_id}",
                    "error": str(exc),
                }
            )
            continue

        for event in events:
            start_obj = event.get("start") or {}
            end_obj = event.get("end") or {}
            summary = (event.get("summary") or "Untitled event").strip()
            out_items.append(
                {
                    "source_calendar_id": calendar_id,
                    "type": classify_event(summary),
                    "title": summary,
                    "date": date_key_from_start(start_obj),
                    "start": start_obj.get("dateTime") or start_obj.get("date", ""),
                    "end": end_obj.get("dateTime") or end_obj.get("date", ""),
                    "location": (event.get("location") or "").strip(),
                    "description": (event.get("description") or "").strip(),
                    "url": event.get("htmlLink", ""),
                }
            )

    out_items.sort(key=lambda item: (item.get("date", ""), item.get("start", ""), item.get("title", "")))
    return {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "items": out_items,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = scrape()
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload.get('items', []))} calendar event(s) to {OUTPUT_FILE}")
    if payload.get("error"):
        print(payload["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

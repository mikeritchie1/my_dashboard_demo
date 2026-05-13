from __future__ import annotations

import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_DIR / "docs" / "data" / "events"
LOCATIONS_CACHE_PATH = OUTPUT_DIR / "locations.json"

# South Africa bounds + safety buffer so clearly wrong geocodes are rejected.
MIN_LAT = -36.5
MAX_LAT = -20.0
MIN_LNG = 14.0
MAX_LNG = 36.0


def normalize_location_key(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def is_valid_sa_coordinate(lat: float | int, lng: float | int) -> bool:
    try:
        lat_value = float(lat)
        lng_value = float(lng)
    except (TypeError, ValueError):
        return False
    if abs(lat_value) < 0.000001 and abs(lng_value) < 0.000001:
        return False
    return MIN_LAT <= lat_value <= MAX_LAT and MIN_LNG <= lng_value <= MAX_LNG


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_payload(payload: dict) -> dict[str, dict[str, float]]:
    cleaned: dict[str, dict[str, float]] = {}
    for raw_key, raw_value in payload.items():
        key = normalize_location_key(str(raw_key or ""))
        if not key or key.lower().startswith("event_url::"):
            continue
        if not isinstance(raw_value, dict):
            continue
        lat = raw_value.get("lat")
        lng = raw_value.get("lng")
        if not is_valid_sa_coordinate(lat, lng):
            continue
        cleaned[key] = {"lat": float(lat), "lng": float(lng)}
    return cleaned


def load_locations_cache() -> dict[str, dict[str, float]]:
    return _clean_payload(_load_json(LOCATIONS_CACHE_PATH))


def save_locations_cache(cache: dict[str, dict[str, float]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = _clean_payload(cache)
    LOCATIONS_CACHE_PATH.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

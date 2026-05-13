from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from env import get as env_get
from location_cache import (
    is_valid_sa_coordinate,
    load_locations_cache,
    normalize_location_key,
    save_locations_cache,
)
from sync_docs import sync_events_data_to_docs


REPO_DIR = Path(__file__).resolve().parents[2]
EVENTS_DIR = REPO_DIR / "docs" / "data" / "events"
LOCATIONS_PATH = EVENTS_DIR / "locations.json"
NOMINATIM_SEARCH_URL = env_get("SCRAPE_NOMINATIM_SEARCH_URL", "https://nominatim.openstreetmap.org/search")
EVENT_SOURCE_FILES = [
    "bandsintown_events.json",
    "quicket_events.json",
    "webtickets_wc_events.json",
]


def geocode_address(query: str) -> tuple[str, dict[str, float] | None]:
    if not query:
        return ("not_found", None)
    url = f"{NOMINATIM_SEARCH_URL}?format=json&limit=1&q={urllib.parse.quote(query)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "my-dashboard/1.0 (contact: local)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or not payload:
        return ("not_found", None)
    first = payload[0]
    try:
        lat = float(first.get("lat"))
        lng = float(first.get("lon"))
    except (TypeError, ValueError):
        return ("not_found", None)
    if not is_valid_sa_coordinate(lat, lng):
        return ("out_of_bounds", {"lat": lat, "lng": lng})
    return ("ok", {"lat": lat, "lng": lng})


def read_json(path: Path) -> object:
    if not path.exists():
        return {} if path.name.endswith(".json") else None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def geocode_location_key(location_key: str, cache: dict[str, dict[str, float]]) -> bool:
    key = normalize_location_key(location_key)
    if not key:
        return False
    if key in cache and is_valid_sa_coordinate(cache[key].get("lat"), cache[key].get("lng")):
        return True
    print(f"Geocoding location: {key}", flush=True)
    status, coords = geocode_address(key)
    time.sleep(1.0)
    if status == "not_found" or not coords:
        print(f"  Not found: {key}", flush=True)
        return False
    if status == "out_of_bounds":
        print(
            f"  Out of bounds for SA: {key} -> ({coords['lat']}, {coords['lng']})",
            flush=True,
        )
        return False
    cache[key] = coords
    save_locations_cache(cache)
    print(f"  Saved: {key} -> ({coords['lat']}, {coords['lng']})", flush=True)
    return True


def update_places(cache: dict[str, dict[str, float]]) -> None:
    places_path = EVENTS_DIR / "places.json"
    payload = read_json(places_path)
    if not isinstance(payload, dict):
        return
    changed = False
    for place_name, place in payload.items():
        if not isinstance(place, dict):
            continue
        name = normalize_location_key(str(place.get("name") or place_name))
        address = normalize_location_key(str(place.get("address") or ""))
        key = name or address
        if not key:
            print(f"Place missing name/address: {place_name}", flush=True)
            continue
        found = geocode_location_key(key, cache)
        if not found and address and address != key:
            found = geocode_location_key(address, cache)
        if found and key not in cache and name and name in cache:
            cache[key] = cache[name]
            save_locations_cache(cache)
    if changed:
        write_json(places_path, payload)
        print(f"Updated places: {places_path}", flush=True)


def update_events(cache: dict[str, dict[str, float]]) -> None:
    places_path = EVENTS_DIR / "places.json"
    places_payload = read_json(places_path)
    places_by_name: dict[str, dict] = {}
    places_by_address: dict[str, dict] = {}
    if isinstance(places_payload, dict):
        for raw_name, item in places_payload.items():
            if not isinstance(item, dict):
                continue
            place_name = normalize_location_key(str(item.get("name") or raw_name))
            place_address = normalize_location_key(str(item.get("address") or ""))
            if place_name:
                places_by_name[place_name.lower()] = item
            if place_address:
                places_by_address[place_address.lower()] = item

    for filename in EVENT_SOURCE_FILES:
        path = EVENTS_DIR / filename
        payload = read_json(path)
        if not isinstance(payload, list):
            continue
        changed = False
        for event in payload:
            if not isinstance(event, dict):
                continue
            label = str(event.get("title") or event.get("venue") or event.get("url") or filename)
            venue_name = normalize_location_key(str(event.get("venue") or ""))
            event_address = normalize_location_key(str(event.get("address") or ""))
            place_key = normalize_location_key(str(event.get("place_key") or ""))
            existing_location_key = normalize_location_key(str(event.get("location_key") or ""))
            matched_place = None
            if place_key:
                matched_place = places_by_name.get(place_key.lower())
            if not matched_place and venue_name:
                matched_place = places_by_name.get(venue_name.lower())
            if not matched_place and event_address:
                matched_place = places_by_address.get(event_address.lower())
            has_place = bool(matched_place)

            if matched_place:
                resolved_place_name = normalize_location_key(str(matched_place.get("name") or ""))
                location_key = resolved_place_name or event_address or venue_name
            else:
                location_key = venue_name or event_address or existing_location_key
            has_location = False
            lookup_order = [location_key, event_address, existing_location_key]
            for key in lookup_order:
                normalized = normalize_location_key(key)
                if not normalized:
                    continue
                if normalized in cache and is_valid_sa_coordinate(cache[normalized].get("lat"), cache[normalized].get("lng")):
                    has_location = True
                    location_key = normalized
                    break
            if not has_location and location_key:
                has_location = geocode_location_key(location_key, cache)
            if not has_location and event_address and event_address != location_key:
                has_location = geocode_location_key(event_address, cache)
            if not has_location and existing_location_key and existing_location_key not in {location_key, event_address}:
                has_location = geocode_location_key(existing_location_key, cache)
            event_missing_place = not has_place
            event_missing_location = not has_location
            if matched_place:
                next_place_key = normalize_location_key(str(matched_place.get("name") or ""))
                next_place = next_place_key
            else:
                next_place_key = ""
                next_place = ""
            if event.get("location_key") != location_key:
                event["location_key"] = location_key
                changed = True
            if str(event.get("place_key") or "").strip() != next_place_key:
                event["place_key"] = next_place_key
                changed = True
            if str(event.get("place") or "").strip() != next_place:
                event["place"] = next_place
                changed = True
            if bool(event.get("missing_place")) != event_missing_place:
                event["missing_place"] = event_missing_place
                changed = True
            if bool(event.get("missing_location")) != event_missing_location:
                event["missing_location"] = event_missing_location
                changed = True
            print(f"Processed event: {label}", flush=True)
        if changed:
            write_json(path, payload)
            print(f"Updated events: {path}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Geocode all event/place location keys and update missing flags.")
    parser.add_argument("--hard", action="store_true", help="Reset locations cache before geocoding.")
    parser.add_argument("--limit", type=int, default=0, help="Accepted for consistency; geocoder processes all entries.")
    parser.add_argument("--source", default="all", help="Accepted for consistency; geocoder always processes all event sources.")
    args = parser.parse_args()

    if args.hard and LOCATIONS_PATH.exists():
        print(f"Removing locations cache for hard geocode: {LOCATIONS_PATH}", flush=True)
        LOCATIONS_PATH.unlink()

    cache = load_locations_cache()
    save_locations_cache(cache)
    update_places(cache)
    update_events(cache)
    sync_events_data_to_docs()
    print("Geocode pass complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

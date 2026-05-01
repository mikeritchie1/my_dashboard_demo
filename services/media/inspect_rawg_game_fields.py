from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[2]))

from services.media.scrape_watchlist import fetch_game_detail, rawg_request, rawg_title_key


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def preview(value: Any, max_length: int = 120) -> str:
    if isinstance(value, str):
        text = value.replace("\r", " ").replace("\n", " ").strip()
    elif isinstance(value, (int, float, bool)) or value is None:
        text = json.dumps(value)
    elif isinstance(value, list):
        text = f"{len(value)} item(s)"
        if value and isinstance(value[0], dict):
            names = [str(item.get("name") or item.get("title") or item.get("slug") or "").strip() for item in value[:5]]
            names = [name for name in names if name]
            if names:
                text += f": {', '.join(names)}"
    elif isinstance(value, dict):
        text = f"{len(value)} field(s)"
    else:
        text = str(value)
    return text[: max_length - 1] + "…" if len(text) > max_length else text


def print_field_tree(value: Any, *, label: str, max_depth: int, depth: int = 0) -> None:
    indent = "  " * depth
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            child = value[key]
            print(f"{indent}- {label}.{key}: {type_name(child)} = {preview(child)}")
            if depth + 1 < max_depth and isinstance(child, (dict, list)):
                print_field_tree(child, label=f"{label}.{key}", max_depth=max_depth, depth=depth + 1)
    elif isinstance(value, list):
        sample = next((item for item in value if item is not None), None)
        print(f"{indent}- {label}[]: {type_name(sample)} = {preview(sample)}")
        if depth + 1 < max_depth and isinstance(sample, (dict, list)):
            print_field_tree(sample, label=f"{label}[]", max_depth=max_depth, depth=depth + 1)


def choose_candidate(candidates: list[dict], title: str, index: int | None) -> dict:
    if index is not None:
        if index < 1 or index > len(candidates):
            raise ValueError(f"--candidate must be between 1 and {len(candidates)}")
        return candidates[index - 1]

    wanted = rawg_title_key(title)
    ranked = []
    for candidate_index, candidate in enumerate(candidates):
        candidate_name = rawg_title_key(candidate.get("name") or "")
        exact = 1 if candidate_name == wanted else 0
        starts = 1 if candidate_name.startswith(wanted) and wanted else 0
        rating_count = int(candidate.get("ratings_count") or 0)
        ranked.append((exact, starts, rating_count, -candidate_index, candidate))
    ranked.sort(reverse=True)
    return ranked[0][4]


def print_candidates(candidates: list[dict]) -> None:
    print("Search candidates")
    for index, candidate in enumerate(candidates, start=1):
        name = candidate.get("name") or "(no name)"
        slug = candidate.get("slug") or "(no slug)"
        released = candidate.get("released") or "unknown date"
        rating = candidate.get("rating")
        ratings_count = candidate.get("ratings_count")
        print(f"{index}. {name} | slug={slug} | released={released} | rating={rating} | ratings_count={ratings_count}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect exactly which RAWG fields are available for a game search/detail response.",
    )
    parser.add_argument("title", help="Game title to search, for example: 'Hades'")
    parser.add_argument("--candidate", type=int, help="Use a specific search result number instead of auto-ranking.")
    parser.add_argument("--page-size", type=int, default=10, help="Number of RAWG search candidates to fetch.")
    parser.add_argument("--max-depth", type=int, default=3, help="How deep to print nested fields.")
    parser.add_argument("--raw-json", action="store_true", help="Print raw selected search/detail JSON payloads.")
    args = parser.parse_args()

    search_payload = rawg_request({"search": args.title, "page_size": str(args.page_size)})
    candidates = search_payload.get("results", []) if isinstance(search_payload, dict) else []
    if not isinstance(candidates, list) or not candidates:
        print("No RAWG search results found. Check RAWG_API_KEY and the title spelling.")
        return 1

    print_candidates(candidates)
    selected = choose_candidate(candidates, args.title, args.candidate)
    slug = str(selected.get("slug") or "").strip()
    print(f"\nSelected candidate: {selected.get('name') or args.title} ({slug or 'no slug'})")

    detail_payload = rawg_request({}, path_suffix=slug) if slug else {}
    if not isinstance(detail_payload, dict) or not detail_payload:
        print("\nNo detail payload returned for the selected candidate.")
        detail_payload = {}

    print("\nSearch result fields")
    print_field_tree(selected, label="search", max_depth=args.max_depth)

    print("\nDetail endpoint fields")
    print_field_tree(detail_payload, label="detail", max_depth=args.max_depth)

    print("\nCurrent dashboard extraction")
    dashboard_fields = fetch_game_detail(args.title, "game_aaa")
    print(json.dumps(dashboard_fields, indent=2, ensure_ascii=False))

    if args.raw_json:
        print("\nRaw selected search JSON")
        print(json.dumps(selected, indent=2, ensure_ascii=False))
        print("\nRaw detail JSON")
        print(json.dumps(detail_payload, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

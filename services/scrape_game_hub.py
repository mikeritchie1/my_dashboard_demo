"""
Game Hub sync service.

Structure:
  data/game_hub/
    config.json          <- lists game folder names
    <game>/
      <module>/          <- inner module folders
        info.json
        pictures/        <- images named  <n>_<title>.<ext>
        manifest.json    <- auto-generated

For each game, scans inner module directories, builds manifest.json per
module, generates modules.json for the game, then copies everything to
docs/data/game_hub/ so the dashboard can serve it.

Usage:
    python services/scrape_game_hub.py
"""

import json
import shutil
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data" / "game_hub"
DOCS_DIR = REPO_DIR / "docs" / "data" / "game_hub"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


def build_manifest(module_dir: Path) -> dict:
    pictures_dir = module_dir / "pictures"
    if not pictures_dir.exists():
        return {"pictures": []}
    pics = []
    for f in pictures_dir.iterdir():
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        parts = f.stem.split("_", 1)
        try:
            order = int(parts[0])
        except ValueError:
            continue
        title = parts[1].replace("_", " ").title() if len(parts) > 1 else ""
        pics.append({"order": order, "filename": f.name, "title": title})
    pics.sort(key=lambda x: x["order"])
    return {"pictures": pics}


def sync_game(game_name: str) -> None:
    game_data_dir = DATA_DIR / game_name
    game_docs_dir = DOCS_DIR / game_name

    modules = sorted(d.name for d in game_data_dir.iterdir() if d.is_dir())

    (game_data_dir / "modules.json").write_text(
        json.dumps({"modules": modules}, indent=2), encoding="utf-8"
    )

    for module_name in modules:
        module_dir = game_data_dir / module_name
        manifest = build_manifest(module_dir)
        (module_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    game_docs_dir.mkdir(parents=True, exist_ok=True)
    for src in game_data_dir.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(game_data_dir)
        dest = game_docs_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def main() -> None:
    config_path = DATA_DIR / "config.json"
    if not config_path.exists():
        print("No config.json found in data/game_hub/", flush=True)
        return

    config = json.loads(config_path.read_text(encoding="utf-8"))
    games = config.get("games", [])

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, DOCS_DIR / "config.json")

    for game_name in games:
        game_data_dir = DATA_DIR / game_name
        if not game_data_dir.is_dir():
            print(f"  Warning: game folder not found: {game_data_dir}", flush=True)
            continue
        sync_game(game_name)
        print(f"  Synced game: {game_name}", flush=True)

    print(f"Game Hub synced to {DOCS_DIR}", flush=True)


if __name__ == "__main__":
    main()

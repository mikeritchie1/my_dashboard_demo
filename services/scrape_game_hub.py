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
DATA_DIR = REPO_DIR / "docs" / "data" / "game_hub"

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


def build_game_manifests(game_name: str) -> None:
    game_dir = DATA_DIR / game_name
    modules = sorted(d.name for d in game_dir.iterdir() if d.is_dir())
    (game_dir / "modules.json").write_text(
        json.dumps({"modules": modules}, indent=2), encoding="utf-8"
    )
    for module_name in modules:
        module_dir = game_dir / module_name
        manifest = build_manifest(module_dir)
        (module_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )


def main() -> None:
    config_path = DATA_DIR / "config.json"
    if not config_path.exists():
        print("No config.json found in docs/data/game_hub/", flush=True)
        return

    config = json.loads(config_path.read_text(encoding="utf-8"))
    games = config.get("games", [])

    for game_name in games:
        game_dir = DATA_DIR / game_name
        if not game_dir.is_dir():
            print(f"  Warning: game folder not found: {game_dir}", flush=True)
            continue
        build_game_manifests(game_name)
        print(f"  Built manifests: {game_name}", flush=True)

    print(f"Game Hub done: {DATA_DIR}", flush=True)


if __name__ == "__main__":
    main()

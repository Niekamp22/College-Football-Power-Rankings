from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_weeks import display_week_for_game


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_current.csv")
DEFAULT_GAMES_PATH = Path("data/cfbd/raw/2026/games.json")
DEFAULT_OUTPUT_ROOT = Path("output/snapshots")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze the current ratings for the next unplayed college football week.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS_PATH)
    parser.add_argument("--games", type=Path, default=DEFAULT_GAMES_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing weekly snapshot.")
    return parser.parse_args()


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def next_prediction_week(games: list[dict[str, Any]], season: int) -> int:
    completed_weeks = [
        display_week_for_game(game)
        for game in games
        if int(game.get("season") or 0) == season
        and game.get("seasonType") == "regular"
        and game.get("completed")
        and (game.get("homeClassification") == "fbs" or game.get("awayClassification") == "fbs")
    ]
    return max(completed_weeks, default=-1) + 1


def snapshot_rankings(
    season: int,
    ratings_path: Path,
    games_path: Path,
    output_root: Path,
    force: bool = False,
) -> Path:
    games = load_json(games_path)
    prediction_week = next_prediction_week(games, season)
    season_root = output_root / str(season)
    season_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = season_root / f"week_{prediction_week:02d}_ratings.csv"
    metadata_path = season_root / f"week_{prediction_week:02d}_metadata.json"

    if snapshot_path.exists() and not force:
        print(f"Preserved existing Week {prediction_week} snapshot at {snapshot_path}")
        return snapshot_path

    shutil.copy2(ratings_path, snapshot_path)
    with ratings_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    metadata = {
        "season": season,
        "prediction_week": prediction_week,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ratings_source": str(ratings_path),
        "teams": len(rows),
        "rating_system": "dual",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved Week {prediction_week} ratings snapshot to {snapshot_path}")
    return snapshot_path


def main() -> None:
    args = parse_args()
    snapshot_rankings(args.season, args.ratings, args.games, args.output_root, args.force)


if __name__ == "__main__":
    main()

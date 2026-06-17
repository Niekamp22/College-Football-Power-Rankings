from __future__ import annotations

import argparse
from pathlib import Path

from cfbd_client import CfbdClient, write_json


DEFAULT_OUTPUT_ROOT = Path("data/cfbd/raw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download CFBD data for the power rankings project.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    games_parser = subparsers.add_parser("games", help="Fetch games and betting lines for a season.")
    games_parser.add_argument("--year", type=int, required=True)
    games_parser.add_argument("--season-type", default="both")
    games_parser.add_argument("--week", type=int)
    games_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    inputs_parser = subparsers.add_parser("ranking-inputs", help="Fetch the main team-level inputs for rankings.")
    inputs_parser.add_argument("--year", type=int, required=True)
    inputs_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    return parser.parse_args()


def season_folder(output_root: Path, year: int) -> Path:
    return output_root / str(year)


def fetch_games(client: CfbdClient, year: int, season_type: str, week: int | None, output_root: Path) -> None:
    output_dir = season_folder(output_root, year)
    games = client.get("/games", year=year, seasonType=season_type, week=week)
    lines = client.get("/lines", year=year, seasonType=season_type, week=week)
    write_json(output_dir / "games.json", games)
    write_json(output_dir / "lines.json", lines)
    print(f"Saved games and lines to {output_dir}")


def fetch_ranking_inputs(client: CfbdClient, year: int, output_root: Path) -> None:
    output_dir = season_folder(output_root, year)
    payloads = {
        "games.json": client.get("/games", year=year, seasonType="both"),
        "lines.json": client.get("/lines", year=year, seasonType="both"),
        "advanced_team_stats.json": client.get("/stats/season/advanced", year=year),
        "wepa.json": client.get("/wepa/team/season", year=year),
        "talent.json": client.get("/talent", year=year),
        "rankings.json": client.get("/rankings", year=year),
    }

    for filename, payload in payloads.items():
        write_json(output_dir / filename, payload)

    print(f"Saved ranking inputs to {output_dir}")


def main() -> None:
    args = parse_args()
    client = CfbdClient()

    if args.command == "games":
        fetch_games(client, args.year, args.season_type, args.week, args.output_root)
        return

    if args.command == "ranking-inputs":
        fetch_ranking_inputs(client, args.year, args.output_root)
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()

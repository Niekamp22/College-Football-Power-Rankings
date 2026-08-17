from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_SCHEDULE_PATH = Path("data/cfbd/raw/2026/games.json")
DEFAULT_OUTPUT_ROOT = Path("output/projections")
HOME_FIELD_ADVANTAGE = 2.5
FCS_BASELINE_RATING = -18.0
MARGIN_STD_DEV = 16.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project FBS win totals from the current power ratings and a future schedule.")
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS_PATH)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE_PATH)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-games", type=int, default=12)
    parser.add_argument(
        "--require-complete-schedules",
        action="store_true",
        help="Exit with an error when any rated FBS team has fewer than the expected number of games.",
    )
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_float(value: Any, default: float = 0.0) -> float:
    if value in ("", None):
        return default
    return float(value)


def win_probability(spread: float) -> float:
    z_score = spread / MARGIN_STD_DEV
    return 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))


def opponent_rating(game: dict[str, Any], side: str, ratings_lookup: dict[str, dict[str, Any]]) -> tuple[float, str]:
    if side == "home":
        opponent_name = game["awayTeam"]
        opponent_classification = game.get("awayClassification")
    else:
        opponent_name = game["homeTeam"]
        opponent_classification = game.get("homeClassification")

    opponent_row = ratings_lookup.get(opponent_name)
    if opponent_row:
        return parse_float(opponent_row["rating"]), opponent_name
    if opponent_classification == "fcs":
        return FCS_BASELINE_RATING, f"{opponent_name} (FCS baseline)"
    return 0.0, f"{opponent_name} (unrated)"


def ensure_team(summary: dict[str, dict[str, Any]], ratings_lookup: dict[str, dict[str, Any]], team_name: str) -> dict[str, Any]:
    if team_name not in summary:
        rating_row = ratings_lookup[team_name]
        summary[team_name] = {
            "team": team_name,
            "conference": rating_row.get("conference", ""),
            "rating": round(parse_float(rating_row["rating"]), 2),
            "projected_wins": 0.0,
            "projected_losses": 0.0,
            "schedule_games": 0,
            "projected_strength_of_schedule": 0.0,
            "average_game_win_probability": 0.0,
            "games": [],
        }
    return summary[team_name]


def build_projections(ratings_rows: list[dict[str, Any]], schedule_games: list[dict[str, Any]], season: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ratings_lookup = {row["team"]: row for row in ratings_rows}
    summary: dict[str, dict[str, Any]] = {}
    game_rows: list[dict[str, Any]] = []

    for game in schedule_games:
        if int(game.get("season") or 0) != season:
            continue
        if game.get("seasonType") != "regular":
            continue
        if game.get("homeClassification") != "fbs" or game.get("awayClassification") != "fbs":
            if game.get("homeClassification") != "fbs":
                continue
        if game.get("homeClassification") != "fbs":
            continue

        week = int(game.get("week") or 0)
        home_team_name = game["homeTeam"]
        away_team_name = game["awayTeam"]
        if home_team_name not in ratings_lookup:
            continue

        home_team = ensure_team(summary, ratings_lookup, home_team_name)

        away_rating, away_display_name = opponent_rating(game, "home", ratings_lookup)
        home_rating = parse_float(ratings_lookup[home_team_name]["rating"])
        home_spread = home_rating - away_rating + (0.0 if game.get("neutralSite") else HOME_FIELD_ADVANTAGE)
        home_win_prob = win_probability(home_spread)

        home_team["projected_wins"] += home_win_prob
        home_team["schedule_games"] += 1
        home_team["projected_strength_of_schedule"] += away_rating
        home_team["games"].append(home_win_prob)

        favorite = home_team_name if home_spread >= 0 else away_display_name
        favorite_spread = round(abs(home_spread), 2)

        game_rows.append(
            {
                "week": week,
                "team": home_team_name,
                "opponent": away_display_name,
                "site": "neutral" if game.get("neutralSite") else "home",
                "team_rating": round(home_rating, 2),
                "opponent_rating": round(away_rating, 2),
                "projected_spread": round(home_spread, 2),
                "favorite": favorite,
                "favorite_spread": favorite_spread,
                "win_probability": round(home_win_prob, 4),
            }
        )

        if away_team_name in ratings_lookup:
            away_team = ensure_team(summary, ratings_lookup, away_team_name)
            away_team["projected_wins"] += 1 - home_win_prob
            away_team["schedule_games"] += 1
            away_team["projected_strength_of_schedule"] += home_rating
            away_team["games"].append(1 - home_win_prob)

            game_rows.append(
                {
                    "week": week,
                    "team": away_team_name,
                    "opponent": home_team_name,
                    "site": "neutral" if game.get("neutralSite") else "away",
                    "team_rating": round(away_rating, 2),
                    "opponent_rating": round(home_rating, 2),
                    "projected_spread": round(-home_spread, 2),
                    "favorite": favorite,
                    "favorite_spread": favorite_spread,
                    "win_probability": round(1 - home_win_prob, 4),
                }
            )

    summary_rows: list[dict[str, Any]] = []
    for team_name, row in summary.items():
        games = int(row["schedule_games"])
        projected_wins = float(row["projected_wins"])
        row["projected_wins"] = round(projected_wins, 2)
        row["projected_losses"] = round(max(0.0, games - projected_wins), 2)
        row["projected_strength_of_schedule"] = round(
            row["projected_strength_of_schedule"] / games if games else 0.0,
            2,
        )
        row["average_game_win_probability"] = round(
            sum(row["games"]) / len(row["games"]) if row["games"] else 0.0,
            4,
        )
        del row["games"]
        summary_rows.append(row)

    summary_rows.sort(key=lambda row: (-float(row["projected_wins"]), -float(row["rating"]), row["team"]))
    game_rows.sort(key=lambda row: (row["team"], int(row["week"]), row["opponent"]))
    return summary_rows, game_rows


def build_schedule_coverage(
    ratings_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    expected_games: int,
) -> list[dict[str, Any]]:
    summaries = {row["team"]: row for row in summary_rows}
    coverage_rows: list[dict[str, Any]] = []

    for rating_row in ratings_rows:
        team = rating_row["team"]
        summary = summaries.get(team, {})
        schedule_games = int(summary.get("schedule_games", 0) or 0)
        if schedule_games < expected_games:
            status = "incomplete"
        elif schedule_games > expected_games:
            status = "extra_games"
        else:
            status = "complete"

        coverage_rows.append(
            {
                "team": team,
                "conference": rating_row.get("conference", ""),
                "rating": rating_row.get("rating", ""),
                "schedule_games": schedule_games,
                "expected_games": expected_games,
                "missing_games": max(0, expected_games - schedule_games),
                "status": status,
            }
        )

    coverage_rows.sort(key=lambda row: (-int(row["missing_games"]), row["conference"], row["team"]))
    return coverage_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    ratings_rows = load_csv(args.ratings)
    schedule_games = load_json(args.schedule)
    summary_rows, game_rows = build_projections(ratings_rows, schedule_games, args.season)
    coverage_rows = build_schedule_coverage(ratings_rows, summary_rows, args.expected_games)
    incomplete_rows = [row for row in coverage_rows if row["status"] == "incomplete"]

    summary_path = args.output_root / f"projected_win_totals_{args.season}.csv"
    games_path = args.output_root / f"projected_games_{args.season}.csv"
    coverage_path = args.output_root / f"schedule_coverage_{args.season}.csv"
    write_csv(summary_path, summary_rows)
    write_csv(games_path, game_rows)
    write_csv(coverage_path, coverage_rows)

    print(f"Saved projected win totals to {summary_path}")
    print(f"Saved projected game probabilities to {games_path}")
    print(f"Saved schedule coverage audit to {coverage_path}")
    if incomplete_rows:
        print()
        print(f"Warning: {len(incomplete_rows)} teams have fewer than {args.expected_games} scheduled games.")
        for row in incomplete_rows[:20]:
            print(f"- {row['team']}: {row['schedule_games']} games")
        if len(incomplete_rows) > 20:
            print(f"- ...and {len(incomplete_rows) - 20} more")
        if args.require_complete_schedules:
            raise SystemExit("Incomplete schedules found. Refresh the schedule data before trusting projections.")


if __name__ == "__main__":
    main()

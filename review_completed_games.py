from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from cfb_weeks import display_week_for_game, week_label
from project_win_totals import HOME_FIELD_ADVANTAGE, FCS_BASELINE_RATING, UNRATED_FBS_BASELINE_RATING, parse_float


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_GAMES_PATH = Path("data/cfbd/raw/2026/games.json")
DEFAULT_LINES_PATH = Path("data/cfbd/raw/2026/lines.json")
DEFAULT_OUTPUT_ROOT = Path("output/reviews")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade completed games against model and market expectations.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS_PATH)
    parser.add_argument("--games", type=Path, default=DEFAULT_GAMES_PATH)
    parser.add_argument("--lines", type=Path, default=DEFAULT_LINES_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else ["season", "display_week", "week_label", "games"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def average_home_spread(line_game: dict[str, Any] | None) -> float | None:
    if not line_game:
        return None
    spreads = [float(line["spread"]) for line in line_game.get("lines", []) if line.get("spread") is not None]
    return average(spreads)


def rating_for_team(team: str, classification: str | None, ratings: dict[str, float]) -> float:
    if team in ratings:
        return ratings[team]
    if classification == "fbs":
        return UNRATED_FBS_BASELINE_RATING
    if classification == "fcs":
        return FCS_BASELINE_RATING
    return 0.0


def correctness(predicted_margin: float, actual_margin: float) -> str:
    if math.isclose(predicted_margin, 0.0) or math.isclose(actual_margin, 0.0):
        return "push"
    return "correct" if (predicted_margin > 0) == (actual_margin > 0) else "wrong"


def edge_result(edge: float | None, actual_vs_market: float | None) -> str:
    if edge is None or actual_vs_market is None:
        return ""
    if math.isclose(edge, 0.0) or math.isclose(actual_vs_market, 0.0):
        return "push"
    return "right_side" if (edge > 0) == (actual_vs_market > 0) else "wrong_side"


def build_line_lookup(lines: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(line["id"]): line for line in lines if line.get("id") is not None}


def grade_games(
    season: int,
    ratings_rows: list[dict[str, Any]],
    games: list[dict[str, Any]],
    lines: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ratings = {row["team"]: parse_float(row["rating"]) for row in ratings_rows}
    line_lookup = build_line_lookup(lines)
    game_rows: list[dict[str, Any]] = []

    for game in games:
        if int(game.get("season") or 0) != season:
            continue
        if game.get("seasonType") != "regular":
            continue
        if not game.get("completed"):
            continue
        if game.get("homeClassification") != "fbs" and game.get("awayClassification") != "fbs":
            continue
        if game.get("homePoints") is None or game.get("awayPoints") is None:
            continue

        home_team = game.get("homeTeam", "")
        away_team = game.get("awayTeam", "")
        home_rating = rating_for_team(home_team, game.get("homeClassification"), ratings)
        away_rating = rating_for_team(away_team, game.get("awayClassification"), ratings)
        home_field = 0.0 if game.get("neutralSite") else HOME_FIELD_ADVANTAGE
        model_home_margin = home_rating - away_rating + home_field
        actual_home_margin = parse_float(game.get("homePoints")) - parse_float(game.get("awayPoints"))

        line_game = line_lookup.get(int(game["id"])) if game.get("id") is not None else None
        market_home_spread = average_home_spread(line_game)
        market_home_margin = -market_home_spread if market_home_spread is not None else None
        model_edge_home = model_home_margin - market_home_margin if market_home_margin is not None else None
        actual_vs_market = actual_home_margin - market_home_margin if market_home_margin is not None else None
        display_week = display_week_for_game(game)

        game_rows.append(
            {
                "season": season,
                "week": game.get("week", ""),
                "display_week": display_week,
                "week_label": week_label(display_week),
                "start_date": game.get("startDate", ""),
                "away_team": away_team,
                "home_team": home_team,
                "neutral_site": bool(game.get("neutralSite", False)),
                "away_points": game.get("awayPoints", ""),
                "home_points": game.get("homePoints", ""),
                "actual_home_margin": round(actual_home_margin, 2),
                "model_home_margin": round(model_home_margin, 2),
                "model_home_spread": round(-model_home_margin, 2),
                "market_home_spread": round(market_home_spread, 2) if market_home_spread is not None else "",
                "market_home_margin": round(market_home_margin, 2) if market_home_margin is not None else "",
                "model_margin_error": round(model_home_margin - actual_home_margin, 2),
                "market_margin_error": round(market_home_margin - actual_home_margin, 2) if market_home_margin is not None else "",
                "absolute_model_error": round(abs(model_home_margin - actual_home_margin), 2),
                "absolute_market_error": round(abs(market_home_margin - actual_home_margin), 2) if market_home_margin is not None else "",
                "winner_model_result": correctness(model_home_margin, actual_home_margin),
                "winner_market_result": correctness(market_home_margin, actual_home_margin) if market_home_margin is not None else "",
                "model_edge_home_points": round(model_edge_home, 2) if model_edge_home is not None else "",
                "model_edge_side": home_team if model_edge_home and model_edge_home > 0 else away_team if model_edge_home and model_edge_home < 0 else "",
                "edge_result": edge_result(model_edge_home, actual_vs_market),
            }
        )

    game_rows.sort(key=lambda row: (int(row["display_week"]), str(row["start_date"]), row["away_team"], row["home_team"]))

    weekly_rows: list[dict[str, Any]] = []
    weeks = sorted({int(row["display_week"]) for row in game_rows})
    for display_week in weeks:
        rows = [row for row in game_rows if int(row["display_week"]) == display_week]
        rows_with_market = [row for row in rows if row["absolute_market_error"] != ""]
        edge_rows = [row for row in rows if row["edge_result"] in ("right_side", "wrong_side")]
        weekly_rows.append(
            {
                "season": season,
                "display_week": display_week,
                "week_label": week_label(display_week),
                "games": len(rows),
                "games_with_market_line": len(rows_with_market),
                "model_margin_mae": round(average([float(row["absolute_model_error"]) for row in rows]) or 0.0, 2),
                "market_margin_mae": round(average([float(row["absolute_market_error"]) for row in rows_with_market]) or 0.0, 2),
                "model_winner_accuracy": round(
                    sum(1 for row in rows if row["winner_model_result"] == "correct") / len(rows),
                    3,
                ),
                "market_winner_accuracy": round(
                    sum(1 for row in rows_with_market if row["winner_market_result"] == "correct") / len(rows_with_market),
                    3,
                )
                if rows_with_market
                else "",
                "edge_right_side_rate": round(
                    sum(1 for row in edge_rows if row["edge_result"] == "right_side") / len(edge_rows),
                    3,
                )
                if edge_rows
                else "",
            }
        )

    return weekly_rows, game_rows


def main() -> None:
    args = parse_args()
    weekly_rows, game_rows = grade_games(
        season=args.season,
        ratings_rows=load_csv(args.ratings),
        games=load_json(args.games),
        lines=load_json(args.lines),
    )

    weekly_path = args.output_root / f"weekly_results_review_{args.season}.csv"
    games_path = args.output_root / f"completed_games_review_{args.season}.csv"
    write_csv(weekly_path, weekly_rows)
    write_csv(games_path, game_rows)
    print(f"Saved weekly results review to {weekly_path}")
    print(f"Saved completed games review to {games_path}")
    print(f"Reviewed {len(game_rows)} completed games.")


if __name__ == "__main__":
    main()

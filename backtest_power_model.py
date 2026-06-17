from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

from build_team_features import apply_talent, build_game_features, load_json, summarize_lines
from power_rankings import average_home_spread, blended_team_ratings, fit_market_model


DEFAULT_RAW_ROOT = Path("data/cfbd/raw")
DEFAULT_OUTPUT_ROOT = Path("output/backtests")

# Only use features that are available without leaking future season information.
BACKTEST_FEATURES = [
    "latest_team_postgame_elo",
    "avg_team_postgame_elo",
    "avg_team_pregame_elo",
    "recent_avg_cover_margin",
    "avg_cover_margin",
    "recent_win_pct",
    "recent_fbs_win_pct",
    "recent_fbs_avg_margin",
    "fbs_avg_margin",
    "avg_opponent_postgame_elo",
    "fbs_avg_opponent_pregame_elo",
    "talent",
]
DEFAULT_PRIOR_DECAY_GAMES = 2.5
DEFAULT_MIN_PRIOR_WEIGHT = 0.0
DEFAULT_PRIOR_SCALE = 14.0
DEFAULT_RIDGE_ALPHA = 0.75


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest the power model week by week on a past season.")
    parser.add_argument("--year", type=int, required=True, help="Season year to backtest.")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT, help="Root folder of downloaded CFBD raw data.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Folder for backtest output files.",
    )
    parser.add_argument(
        "--season-type",
        choices=["regular", "postseason", "both"],
        default="regular",
        help="Season type to backtest.",
    )
    parser.add_argument("--min-week", type=int, default=2, help="First week to evaluate.")
    parser.add_argument("--max-week", type=int, help="Last week to evaluate.")
    parser.add_argument("--prior-decay-games", type=float, default=DEFAULT_PRIOR_DECAY_GAMES)
    parser.add_argument("--min-prior-weight", type=float, default=DEFAULT_MIN_PRIOR_WEIGHT)
    parser.add_argument("--prior-scale", type=float, default=DEFAULT_PRIOR_SCALE)
    parser.add_argument("--ridge-alpha", type=float, default=DEFAULT_RIDGE_ALPHA)
    parser.add_argument(
        "--save-games",
        action="store_true",
        help="Also save game-level prediction errors alongside weekly summaries.",
    )
    return parser.parse_args()


def safe_corr(x_values: list[float], y_values: list[float]) -> float:
    if len(x_values) < 2 or len(y_values) < 2:
        return 0.0
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    x_var = sum((value - x_mean) ** 2 for value in x_values)
    y_var = sum((value - y_mean) ** 2 for value in y_values)
    if math.isclose(x_var, 0.0) or math.isclose(y_var, 0.0):
        return 0.0
    covariance = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    return covariance / math.sqrt(x_var * y_var)


def mae(errors: list[float]) -> float:
    return sum(abs(error) for error in errors) / len(errors) if errors else 0.0


def rmse(errors: list[float]) -> float:
    return math.sqrt(sum(error**2 for error in errors) / len(errors)) if errors else 0.0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def filter_rows(items: list[dict[str, Any]], season_type: str, week_cmp) -> list[dict[str, Any]]:
    def matches(item: dict[str, Any]) -> bool:
        item_type = item.get("seasonType")
        if season_type != "both" and item_type != season_type:
            return False
        return week_cmp(int(item.get("week") or 0))

    return [item for item in items if matches(item)]


def build_training_rows(
    games: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    talent_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    line_lookup = summarize_lines(lines)
    features = build_game_features(games, line_lookup)
    apply_talent(features, talent_rows)
    return sorted(
        (row for row in features.values() if row.get("classification") == "fbs"),
        key=lambda row: str(row["team"]),
    )


def run_backtest(
    year: int,
    raw_root: Path,
    season_type: str,
    min_week: int,
    max_week: int | None,
    prior_decay_games: float,
    min_prior_weight: float,
    prior_scale: float,
    ridge_alpha: float,
    save_games: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = raw_root / str(year)

    games = load_json(base / "games.json")
    lines = load_json(base / "lines.json")
    talent_rows = load_json(base / "talent.json")

    all_weeks = sorted(
        {
            int(item.get("week") or 0)
            for item in lines
            if season_type == "both" or item.get("seasonType") == season_type
        }
    )
    if not all_weeks:
        return [], []

    final_week = max_week if max_week is not None else max(all_weeks)
    evaluation_weeks = [week for week in all_weeks if min_week <= week <= final_week]
    if not evaluation_weeks:
        return [], []

    weekly_rows: list[dict[str, Any]] = []
    game_rows: list[dict[str, Any]] = []

    for week in evaluation_weeks:
        training_games = filter_rows(games, season_type, lambda current_week: current_week < week)
        training_lines = filter_rows(lines, season_type, lambda current_week: current_week < week)
        eval_lines = filter_rows(lines, season_type, lambda current_week: current_week == week)

        training_rows = build_training_rows(training_games, training_lines, talent_rows)
        if len(training_rows) < 10:
            continue

        feature_coefficients, home_field_advantage, _, team_vectors, diagnostics = fit_market_model(
            training_rows,
            training_lines,
            calibration_features=BACKTEST_FEATURES,
            ridge_alpha=ridge_alpha,
        )

        ratings = blended_team_ratings(
            training_rows,
            feature_coefficients,
            team_vectors,
            calibration_features=BACKTEST_FEATURES,
            prior_decay_games=prior_decay_games,
            min_prior_weight=min_prior_weight,
            prior_scale=prior_scale,
        )

        model_market_errors: list[float] = []
        model_actual_errors: list[float] = []
        actual_market_errors: list[float] = []
        model_margins: list[float] = []
        market_margins: list[float] = []
        actual_margins: list[float] = []

        for game in eval_lines:
            if game.get("homeClassification") != "fbs" or game.get("awayClassification") != "fbs":
                continue

            home_team = game.get("homeTeam")
            away_team = game.get("awayTeam")
            if home_team not in ratings or away_team not in ratings:
                continue

            home_spread = average_home_spread(game)
            if home_spread is None or game.get("homeScore") is None or game.get("awayScore") is None:
                continue

            model_home_margin = ratings[home_team] - ratings[away_team] + home_field_advantage
            market_home_margin = -home_spread
            actual_home_margin = float(game["homeScore"]) - float(game["awayScore"])

            model_market_error = model_home_margin - market_home_margin
            model_actual_error = model_home_margin - actual_home_margin
            actual_market_error = actual_home_margin - market_home_margin

            model_market_errors.append(model_market_error)
            model_actual_errors.append(model_actual_error)
            actual_market_errors.append(actual_market_error)
            model_margins.append(model_home_margin)
            market_margins.append(market_home_margin)
            actual_margins.append(actual_home_margin)

            if save_games:
                game_rows.append(
                    {
                        "year": year,
                        "week": week,
                        "home_team": home_team,
                        "away_team": away_team,
                        "model_home_margin": round(model_home_margin, 3),
                        "market_home_margin": round(market_home_margin, 3),
                        "actual_home_margin": round(actual_home_margin, 3),
                        "model_vs_market_error": round(model_market_error, 3),
                        "model_vs_actual_error": round(model_actual_error, 3),
                        "actual_vs_market_error": round(actual_market_error, 3),
                    }
                )

        if not model_market_errors:
            continue

        weekly_rows.append(
            {
                "year": year,
                "season_type": season_type,
                "week": week,
                "games": len(model_market_errors),
                "train_samples": diagnostics["samples"],
                "home_field_advantage": round(home_field_advantage, 3),
                "prior_decay_games": round(prior_decay_games, 3),
                "min_prior_weight": round(min_prior_weight, 3),
                "prior_scale": round(prior_scale, 3),
                "ridge_alpha": round(ridge_alpha, 3),
                "model_vs_market_mae": round(mae(model_market_errors), 3),
                "model_vs_market_rmse": round(rmse(model_market_errors), 3),
                "model_vs_market_corr": round(safe_corr(model_margins, market_margins), 3),
                "model_vs_actual_mae": round(mae(model_actual_errors), 3),
                "model_vs_actual_rmse": round(rmse(model_actual_errors), 3),
                "model_vs_actual_corr": round(safe_corr(model_margins, actual_margins), 3),
                "actual_vs_market_mae": round(mae(actual_market_errors), 3),
                "actual_vs_market_rmse": round(rmse(actual_market_errors), 3),
                "actual_vs_market_corr": round(safe_corr(actual_margins, market_margins), 3),
            }
        )

    return weekly_rows, game_rows


def main() -> None:
    args = parse_args()
    weekly_rows, game_rows = run_backtest(
        year=args.year,
        raw_root=args.raw_root,
        season_type=args.season_type,
        min_week=args.min_week,
        max_week=args.max_week,
        prior_decay_games=args.prior_decay_games,
        min_prior_weight=args.min_prior_weight,
        prior_scale=args.prior_scale,
        ridge_alpha=args.ridge_alpha,
        save_games=args.save_games,
    )
    if not weekly_rows:
        raise SystemExit("No backtest results were produced for the requested settings.")

    label = f"{args.year}_{args.season_type}"
    weekly_path = args.output_root / f"weekly_backtest_{label}.csv"
    write_csv(weekly_path, weekly_rows)

    print(f"Saved weekly backtest summary to {weekly_path}")
    print()
    print("Weekly backtest snapshot")
    print(f"{'WK':<4}{'G':<5}{'MVSM_MAE':<12}{'MVSA_MAE':<12}{'AVSM_MAE':<12}{'CORR':<8}")
    for row in weekly_rows:
        print(
            f"{int(row['week']):<4}"
            f"{int(row['games']):<5}"
            f"{float(row['model_vs_market_mae']):<12.3f}"
            f"{float(row['model_vs_actual_mae']):<12.3f}"
            f"{float(row['actual_vs_market_mae']):<12.3f}"
            f"{float(row['model_vs_market_corr']):<8.3f}"
        )

    overall_games = sum(int(row["games"]) for row in weekly_rows)
    weighted_model_market_mae = sum(float(row["model_vs_market_mae"]) * int(row["games"]) for row in weekly_rows) / overall_games
    weighted_model_actual_mae = sum(float(row["model_vs_actual_mae"]) * int(row["games"]) for row in weekly_rows) / overall_games
    weighted_actual_market_mae = sum(float(row["actual_vs_market_mae"]) * int(row["games"]) for row in weekly_rows) / overall_games

    print()
    print(
        f"Overall: games {overall_games}, "
        f"model-market MAE {weighted_model_market_mae:.3f}, "
        f"model-actual MAE {weighted_model_actual_mae:.3f}, "
        f"actual-market MAE {weighted_actual_market_mae:.3f}"
    )

    if args.save_games and game_rows:
        game_path = args.output_root / f"game_backtest_{label}.csv"
        write_csv(game_path, game_rows)
        print(f"Saved game-level backtest details to {game_path}")


if __name__ == "__main__":
    main()

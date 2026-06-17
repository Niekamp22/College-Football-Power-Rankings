from __future__ import annotations

import argparse
import csv
from pathlib import Path

from backtest_power_model import run_backtest


DEFAULT_RAW_ROOT = Path("data/cfbd/raw")
DEFAULT_OUTPUT_PATH = Path("output/backtests/tuning_results.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune prior-blend settings across multiple seasons.")
    parser.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025])
    parser.add_argument("--season-type", choices=["regular", "postseason", "both"], default="regular")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--market-weight", type=float, default=0.7, help="Weight on model-vs-market MAE in the blended score.")
    parser.add_argument("--actual-weight", type=float, default=0.3, help="Weight on model-vs-actual MAE in the blended score.")
    parser.add_argument(
        "--sort-by",
        choices=["market", "actual", "blended"],
        default="blended",
        help="Primary objective for ranking candidates.",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    total_weight = args.market_weight + args.actual_weight
    if total_weight <= 0:
        raise SystemExit("The market and actual weights must add up to a positive number.")
    market_weight = args.market_weight / total_weight
    actual_weight = args.actual_weight / total_weight

    prior_decay_candidates = [2.5, 4.0, 5.0, 6.5]
    min_prior_candidates = [0.0, 0.05, 0.08, 0.12]
    prior_scale_candidates = [8.0, 10.0, 12.0, 14.0]
    ridge_alpha_candidates = [0.1, 0.2, 0.35, 0.5, 0.75, 1.0]

    results: list[dict] = []
    for prior_decay_games in prior_decay_candidates:
        for min_prior_weight in min_prior_candidates:
            for prior_scale in prior_scale_candidates:
                for ridge_alpha in ridge_alpha_candidates:
                    total_games = 0
                    weighted_market_mae = 0.0
                    weighted_actual_mae = 0.0
                    weighted_corr = 0.0

                    for year in args.years:
                        weekly_rows, _ = run_backtest(
                            year=year,
                            raw_root=DEFAULT_RAW_ROOT,
                            season_type=args.season_type,
                            min_week=2,
                            max_week=None,
                            prior_decay_games=prior_decay_games,
                            min_prior_weight=min_prior_weight,
                            prior_scale=prior_scale,
                            ridge_alpha=ridge_alpha,
                            save_games=False,
                        )
                        for row in weekly_rows:
                            games = int(row["games"])
                            total_games += games
                            weighted_market_mae += float(row["model_vs_market_mae"]) * games
                            weighted_actual_mae += float(row["model_vs_actual_mae"]) * games
                            weighted_corr += float(row["model_vs_market_corr"]) * games

                    if not total_games:
                        continue

                    market_mae = weighted_market_mae / total_games
                    actual_mae = weighted_actual_mae / total_games
                    blended_mae = (market_weight * market_mae) + (actual_weight * actual_mae)

                    results.append(
                        {
                            "years": ",".join(str(year) for year in args.years),
                            "prior_decay_games": prior_decay_games,
                            "min_prior_weight": min_prior_weight,
                            "prior_scale": prior_scale,
                            "ridge_alpha": ridge_alpha,
                            "games": total_games,
                            "market_weight": round(market_weight, 4),
                            "actual_weight": round(actual_weight, 4),
                            "weighted_model_vs_market_mae": round(market_mae, 4),
                            "weighted_model_vs_actual_mae": round(actual_mae, 4),
                            "weighted_blended_mae": round(blended_mae, 4),
                            "weighted_model_vs_market_corr": round(weighted_corr / total_games, 4),
                        }
                    )

    sort_key = {
        "market": "weighted_model_vs_market_mae",
        "actual": "weighted_model_vs_actual_mae",
        "blended": "weighted_blended_mae",
    }[args.sort_by]
    results.sort(key=lambda row: (float(row[sort_key]), float(row["weighted_model_vs_market_mae"]), -float(row["weighted_model_vs_market_corr"])))
    write_csv(args.output, results)

    print(f"Saved tuning results to {args.output}")
    print()
    print("Top candidates")
    for row in results[:10]:
        print(row)


if __name__ == "__main__":
    main()

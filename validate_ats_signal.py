from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import numpy as np

from backtest_power_model import run_backtest


DEFAULT_OUTPUT = Path("output/analytics/ats_model_validation.csv")
FEATURES = [
    "abs_edge",
    "pick_home",
    "pick_spread",
    "football_pick_edge",
    "market_pick_edge",
    "component_agree",
    "week",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an ATS classifier on a held-out season.")
    parser.add_argument("--train-years", nargs="+", type=int, default=[2023, 2024])
    parser.add_argument("--test-year", type=int, default=2025)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def build_rows(years: list[int]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for year in years:
        _, games = run_backtest(
            year=year,
            raw_root=Path("data/cfbd/raw"),
            season_type="regular",
            min_week=2,
            max_week=None,
            prior_decay_games=2.5,
            min_prior_weight=0.0,
            prior_scale=14.0,
            ridge_alpha=0.75,
            save_games=True,
            rating_system="dual",
            football_weight=0.60,
            market_weight=0.40,
        )
        for game in games:
            edge = float(game["model_home_margin"]) - float(game["market_home_margin"])
            actual_vs_market = float(game["actual_home_margin"]) - float(game["market_home_margin"])
            if edge == 0 or actual_vs_market == 0:
                continue
            pick_sign = 1.0 if edge > 0 else -1.0
            rows.append(
                {
                    "year": float(year),
                    "target": float(edge * actual_vs_market > 0),
                    "abs_edge": abs(edge),
                    "pick_home": float(edge > 0),
                    "pick_spread": (-float(game["market_home_margin"]) if edge > 0 else float(game["market_home_margin"])),
                    "football_pick_edge": (float(game["football_home_margin"]) - float(game["market_home_margin"])) * pick_sign,
                    "market_pick_edge": (float(game["market_component_home_margin"]) - float(game["market_home_margin"])) * pick_sign,
                    "component_agree": float(
                        ((float(game["football_home_margin"]) - float(game["market_home_margin"])) * pick_sign > 0)
                        and ((float(game["market_component_home_margin"]) - float(game["market_home_margin"])) * pick_sign > 0)
                    ),
                    "week": float(game["week"]),
                }
            )
    return rows


def matrix(rows: list[dict[str, float]], means: np.ndarray, std_devs: np.ndarray) -> np.ndarray:
    values = np.array([[row[feature] for feature in FEATURES] for row in rows], dtype=float)
    return np.column_stack([np.ones(len(rows)), (values - means) / std_devs])


def fit_logistic(x_matrix: np.ndarray, targets: np.ndarray, ridge: float = 5.0) -> np.ndarray:
    coefficients = np.zeros(x_matrix.shape[1], dtype=float)
    for _ in range(50):
        probabilities = 1 / (1 + np.exp(-np.clip(x_matrix @ coefficients, -30, 30)))
        weights = probabilities * (1 - probabilities)
        gradient = x_matrix.T @ (probabilities - targets) + ridge * np.r_[0.0, coefficients[1:]]
        hessian = x_matrix.T @ (x_matrix * weights[:, None]) + ridge * np.diag(np.r_[0.0, np.ones(len(coefficients) - 1)])
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return coefficients


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    train_rows = build_rows(args.train_years)
    test_rows = build_rows([args.test_year])
    train_values = np.array([[row[feature] for feature in FEATURES] for row in train_rows], dtype=float)
    means = train_values.mean(axis=0)
    std_devs = train_values.std(axis=0)
    std_devs[std_devs == 0] = 1.0
    train_x = matrix(train_rows, means, std_devs)
    test_x = matrix(test_rows, means, std_devs)
    train_y = np.array([row["target"] for row in train_rows], dtype=float)
    test_y = np.array([row["target"] for row in test_rows], dtype=float)
    coefficients = fit_logistic(train_x, train_y)
    test_probabilities = 1 / (1 + np.exp(-np.clip(test_x @ coefficients, -30, 30)))
    model_brier = float(np.mean((test_probabilities - test_y) ** 2))
    baseline_probability = float(train_y.mean())
    baseline_brier = float(np.mean((baseline_probability - test_y) ** 2))
    validated = model_brier < baseline_brier

    output_rows: list[dict[str, Any]] = []
    for threshold in [0.50, 0.515, 0.524, 0.53, 0.55]:
        selected = test_probabilities >= threshold
        picks = int(selected.sum())
        output_rows.append(
            {
                "train_years": ",".join(str(year) for year in args.train_years),
                "test_year": args.test_year,
                "validated_for_deployment": validated,
                "model_brier": round(model_brier, 6),
                "baseline_brier": round(baseline_brier, 6),
                "probability_threshold": threshold,
                "picks": picks,
                "hit_rate": round(float(test_y[selected].mean()), 4) if picks else "",
                "average_predicted_probability": round(float(test_probabilities[selected].mean()), 4) if picks else "",
                "status": "Eligible for deployment" if validated else "Not deployed - failed held-out Brier test",
            }
        )
    write_csv(args.output, output_rows)
    print(f"Saved ATS validation to {args.output}")
    print(f"Held-out Brier: model {model_brier:.6f}, baseline {baseline_brier:.6f}, deployed {validated}")


if __name__ == "__main__":
    main()

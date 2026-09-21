from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from dual_ratings import average_home_spread


DEFAULT_RAW_ROOT = Path("data/cfbd/raw")
DEFAULT_OUTPUT = Path("output/analytics/margin_challenger_validation.csv")
FEATURE_NAMES = [
    "elo_difference",
    "talent_difference",
    "season_matchup_margin",
    "recent_matchup_margin",
    "season_margin_difference",
    "recent_margin_difference",
    "win_pct_difference",
    "rest_difference",
    "experience",
    "home_field",
    "conference_game",
    "market_margin",
    "market_magnitude",
    "week",
]


@dataclass
class TeamState:
    games: int = 0
    wins: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    margin_sum: float = 0.0
    recent_points_for: list[float] = field(default_factory=list)
    recent_points_against: list[float] = field(default_factory=list)
    recent_margins: list[float] = field(default_factory=list)
    last_game: datetime | None = None

    def update(self, points_for: float, points_against: float, played_at: datetime) -> None:
        margin = points_for - points_against
        self.games += 1
        self.wins += int(margin > 0)
        self.points_for += points_for
        self.points_against += points_against
        self.margin_sum += margin
        self.recent_points_for = (self.recent_points_for + [points_for])[-4:]
        self.recent_points_against = (self.recent_points_against + [points_against])[-4:]
        self.recent_margins = (self.recent_margins + [margin])[-4:]
        self.last_game = played_at


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def mean(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


def state_values(state: TeamState, league_points: float) -> dict[str, float]:
    games = max(state.games, 1)
    return {
        "offense": state.points_for / games if state.games else league_points,
        "defense_allowed": state.points_against / games if state.games else league_points,
        "margin": state.margin_sum / games if state.games else 0.0,
        "recent_offense": mean(state.recent_points_for, league_points),
        "recent_defense_allowed": mean(state.recent_points_against, league_points),
        "recent_margin": mean(state.recent_margins, 0.0),
        "win_pct": state.wins / games if state.games else 0.5,
    }


def rest_days(state: TeamState, kickoff: datetime) -> float:
    if state.last_game is None:
        return 7.0
    return min(max((kickoff - state.last_game).total_seconds() / 86400.0, 3.0), 21.0)


def build_season_rows(raw_root: Path, year: int) -> list[dict[str, Any]]:
    base = raw_root / str(year)
    games = json.loads((base / "games.json").read_text(encoding="utf-8"))
    lines = json.loads((base / "lines.json").read_text(encoding="utf-8"))
    talent_rows = json.loads((base / "talent.json").read_text(encoding="utf-8"))
    line_lookup = {str(game["id"]): game for game in lines}
    talent = {str(row["team"]): float(row["talent"]) for row in talent_rows}
    states: dict[str, TeamState] = {}
    rows: list[dict[str, Any]] = []
    total_points = 0.0
    total_team_games = 0

    eligible = [
        game
        for game in games
        if game.get("seasonType") == "regular"
        and game.get("completed")
        and game.get("homeClassification") == "fbs"
        and game.get("awayClassification") == "fbs"
        and game.get("homePoints") is not None
        and game.get("awayPoints") is not None
    ]
    weeks = sorted({int(game.get("week") or 0) for game in eligible})
    for week in weeks:
        week_games = [game for game in eligible if int(game.get("week") or 0) == week]
        league_points = total_points / total_team_games if total_team_games else 28.0
        for game in week_games:
            line_game = line_lookup.get(str(game["id"]))
            if not line_game:
                continue
            home_spread = average_home_spread(line_game)
            if home_spread is None:
                continue

            home_team = str(game["homeTeam"])
            away_team = str(game["awayTeam"])
            home_state = states.setdefault(home_team, TeamState())
            away_state = states.setdefault(away_team, TeamState())
            home_values = state_values(home_state, league_points)
            away_values = state_values(away_state, league_points)
            kickoff = parse_date(str(game["startDate"]))
            neutral = bool(game.get("neutralSite"))
            home_field = 0.0 if neutral else 1.0
            season_matchup = (
                (home_values["offense"] + away_values["defense_allowed"]) / 2
                - (away_values["offense"] + home_values["defense_allowed"]) / 2
            )
            recent_matchup = (
                (home_values["recent_offense"] + away_values["recent_defense_allowed"]) / 2
                - (away_values["recent_offense"] + home_values["recent_defense_allowed"]) / 2
            )
            market_margin = -float(home_spread)
            feature_values = [
                (float(game.get("homePregameElo") or 1500) - float(game.get("awayPregameElo") or 1500)) / 100.0,
                (talent.get(home_team, 700.0) - talent.get(away_team, 700.0)) / 100.0,
                season_matchup,
                recent_matchup,
                home_values["margin"] - away_values["margin"],
                home_values["recent_margin"] - away_values["recent_margin"],
                home_values["win_pct"] - away_values["win_pct"],
                rest_days(home_state, kickoff) - rest_days(away_state, kickoff),
                min(home_state.games, away_state.games) / 5.0,
                home_field,
                float(bool(game.get("conferenceGame"))),
                market_margin,
                abs(market_margin),
                week / 15.0,
            ]
            actual_margin = float(game["homePoints"]) - float(game["awayPoints"])
            rows.append(
                {
                    "year": year,
                    "week": week,
                    "home_team": home_team,
                    "away_team": away_team,
                    "market_margin": market_margin,
                    "actual_margin": actual_margin,
                    "features": feature_values,
                }
            )

        for game in week_games:
            home_team = str(game["homeTeam"])
            away_team = str(game["awayTeam"])
            kickoff = parse_date(str(game["startDate"]))
            home_points = float(game["homePoints"])
            away_points = float(game["awayPoints"])
            states.setdefault(home_team, TeamState()).update(home_points, away_points, kickoff)
            states.setdefault(away_team, TeamState()).update(away_points, home_points, kickoff)
            total_points += home_points + away_points
            total_team_games += 2
    return rows


def matrices(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.array([row["features"] for row in rows], dtype=float)
    market = np.array([row["market_margin"] for row in rows], dtype=float)
    actual = np.array([row["actual_margin"] for row in rows], dtype=float)
    return x, market, actual


def fit_huber_ridge(
    x: np.ndarray,
    target: np.ndarray,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = x.mean(axis=0)
    scales = x.std(axis=0)
    scales[scales < 1e-8] = 1.0
    design = np.column_stack([np.ones(len(x)), (x - means) / scales])
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    weights = np.ones(len(x))
    coefficients = np.zeros(design.shape[1])
    for _ in range(20):
        weighted_design = design * weights[:, None]
        coefficients = np.linalg.solve(design.T @ weighted_design + penalty, design.T @ (weights * target))
        residuals = target - design @ coefficients
        robust_scale = np.median(np.abs(residuals - np.median(residuals))) / 0.6745
        if robust_scale < 1e-8:
            break
        threshold = 1.5 * robust_scale
        weights = np.minimum(1.0, threshold / np.maximum(np.abs(residuals), 1e-8))
    return coefficients, means, scales


def predict(x: np.ndarray, model: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    coefficients, means, scales = model
    design = np.column_stack([np.ones(len(x)), (x - means) / scales])
    return design @ coefficients


def mae(prediction: np.ndarray, actual: np.ndarray) -> float:
    return float(np.mean(np.abs(prediction - actual)))


def evaluate_candidate(
    train_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    alpha: float,
    blend: float,
    correction_cap: float,
) -> dict[str, float]:
    train_x, train_market, train_actual = matrices(train_rows)
    x, market, actual = matrices(rows)
    model = fit_huber_ridge(train_x, train_actual - train_market, alpha)
    raw_correction = predict(x, model)
    correction = np.clip(raw_correction, -correction_cap, correction_cap) * blend
    challenger = market + correction
    edge = challenger - market
    ats_mask = np.abs(edge) >= 2.5
    ats_hits = ((actual - market) * edge > 0)[ats_mask]
    return {
        "games": float(len(rows)),
        "market_mae": mae(market, actual),
        "challenger_mae": mae(challenger, actual),
        "mae_improvement": mae(market, actual) - mae(challenger, actual),
        "ats_picks": float(np.sum(ats_mask)),
        "ats_hit_rate": float(np.mean(ats_hits)) if len(ats_hits) else 0.0,
        "average_abs_correction": float(np.mean(np.abs(correction))),
    }


def run_validation(raw_root: Path = DEFAULT_RAW_ROOT) -> list[dict[str, Any]]:
    season_rows = {year: build_season_rows(raw_root, year) for year in (2023, 2024, 2025)}
    tuning_train = season_rows[2023]
    validation = season_rows[2024]
    candidates: list[dict[str, Any]] = []
    for alpha in (1.0, 5.0, 10.0, 25.0, 50.0, 100.0):
        for blend in (0.25, 0.5, 0.75, 1.0):
            for cap in (3.0, 5.0, 7.0):
                metrics = evaluate_candidate(tuning_train, validation, alpha, blend, cap)
                candidates.append({"alpha": alpha, "blend": blend, "correction_cap": cap, **metrics})
    candidates.sort(key=lambda row: (-float(row["mae_improvement"]), -float(row["ats_hit_rate"])))
    best = candidates[0]

    final_train = season_rows[2023] + season_rows[2024]
    test_metrics = evaluate_candidate(
        final_train,
        season_rows[2025],
        float(best["alpha"]),
        float(best["blend"]),
        float(best["correction_cap"]),
    )
    deployed = test_metrics["mae_improvement"] >= 0.10 and test_metrics["ats_hit_rate"] >= 0.52
    return [
        {
            "stage": "2024_validation",
            "alpha": best["alpha"],
            "blend": best["blend"],
            "correction_cap": best["correction_cap"],
            **{key: round(value, 6) for key, value in best.items() if key not in {"alpha", "blend", "correction_cap"}},
            "deployed": False,
        },
        {
            "stage": "2025_held_out_test",
            "alpha": best["alpha"],
            "blend": best["blend"],
            "correction_cap": best["correction_cap"],
            **{key: round(value, 6) for key, value in test_metrics.items()},
            "deployed": deployed,
        },
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a leakage-safe market-residual margin challenger.")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = run_validation(args.raw_root)
    write_csv(args.output, rows)
    for row in rows:
        print(row)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

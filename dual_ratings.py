from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


FOOTBALL_WEIGHT = 0.60
MARKET_WEIGHT = 0.40
ACTUAL_MARGIN_CAP = 35.0
FOOTBALL_RIDGE_STRENGTH = 2.5
MARKET_RIDGE_STRENGTH = 1.0
HOME_FIELD_PRIOR = 2.5
HOME_FIELD_RIDGE_STRENGTH = 12.0
PRIOR_POINT_SCALE = 8.0


def parse_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def centered(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    average = sum(values.values()) / len(values)
    return {team: value - average for team, value in values.items()}


def z_scores(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    available = [parse_float(row.get(field)) for row in rows if row.get(field) not in (None, "")]
    if not available:
        return {str(row["team"]): 0.0 for row in rows}
    average = sum(available) / len(available)
    variance = sum((value - average) ** 2 for value in available) / len(available)
    std_dev = math.sqrt(variance)
    if math.isclose(std_dev, 0.0):
        return {str(row["team"]): 0.0 for row in rows}
    return {
        str(row["team"]): (parse_float(row.get(field), average) - average) / std_dev
        for row in rows
    }


def prior_ratings(rows: list[dict[str, Any]]) -> dict[str, float]:
    elo = z_scores(rows, "latest_team_postgame_elo")
    talent = z_scores(rows, "talent")
    priors = {
        str(row["team"]): PRIOR_POINT_SCALE * ((0.75 * elo[str(row["team"])]) + (0.25 * talent[str(row["team"])]))
        for row in rows
    }
    return centered(priors)


def average_home_spread(game: dict[str, Any]) -> float | None:
    spreads = [provider.get("spread") for provider in game.get("lines", []) if provider.get("spread") is not None]
    if not spreads:
        return None
    return sum(float(spread) for spread in spreads) / len(spreads)


def solve_team_ratings(
    teams: list[str],
    observations: Iterable[tuple[str, str, float]],
    priors: dict[str, float],
    ridge_strength: float,
) -> tuple[dict[str, float], float, dict[str, float]]:
    team_index = {team: index for index, team in enumerate(teams)}
    usable = [row for row in observations if row[0] in team_index and row[1] in team_index]
    if not usable:
        return centered({team: priors.get(team, 0.0) for team in teams}), HOME_FIELD_PRIOR, {
            "samples": 0,
            "mae": 0.0,
            "rmse": 0.0,
            "correlation": 0.0,
        }

    design = np.zeros((len(usable), len(teams) + 1), dtype=float)
    targets = np.zeros(len(usable), dtype=float)
    for row_index, (home_team, away_team, margin) in enumerate(usable):
        design[row_index, 0] = 1.0
        design[row_index, team_index[home_team] + 1] = 1.0
        design[row_index, team_index[away_team] + 1] = -1.0
        targets[row_index] = margin

    penalty = np.eye(len(teams) + 1, dtype=float) * ridge_strength
    penalty[0, 0] = HOME_FIELD_RIDGE_STRENGTH
    prior_vector = np.array(
        [HOME_FIELD_PRIOR, *[priors.get(team, 0.0) for team in teams]],
        dtype=float,
    )
    rhs = design.T @ targets + penalty @ prior_vector
    coefficients = np.linalg.solve(design.T @ design + penalty, rhs)

    predictions = design @ coefficients
    errors = predictions - targets
    correlation = float(np.corrcoef(predictions, targets)[0, 1]) if len(targets) > 1 else 0.0
    ratings = centered({team: float(coefficients[index + 1]) for team, index in team_index.items()})
    diagnostics = {
        "samples": float(len(usable)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "correlation": correlation if not math.isnan(correlation) else 0.0,
    }
    return ratings, float(coefficients[0]), diagnostics


def football_observations(games: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    observations: list[tuple[str, str, float]] = []
    for game in games:
        if game.get("homeClassification") != "fbs" or game.get("awayClassification") != "fbs":
            continue
        if not game.get("completed") or game.get("homePoints") is None or game.get("awayPoints") is None:
            continue
        actual_margin = float(game["homePoints"]) - float(game["awayPoints"])
        capped_margin = max(-ACTUAL_MARGIN_CAP, min(ACTUAL_MARGIN_CAP, actual_margin))
        observations.append((str(game["homeTeam"]), str(game["awayTeam"]), capped_margin))
    return observations


def market_observations(lines: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    observations: list[tuple[str, str, float]] = []
    for game in lines:
        if game.get("homeClassification") != "fbs" or game.get("awayClassification") != "fbs":
            continue
        home_spread = average_home_spread(game)
        if home_spread is None:
            continue
        observations.append((str(game["homeTeam"]), str(game["awayTeam"]), -home_spread))
    return observations


def build_dual_ratings(
    rows: list[dict[str, Any]],
    games: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    football_weight: float = FOOTBALL_WEIGHT,
    market_weight: float = MARKET_WEIGHT,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    total_weight = football_weight + market_weight
    if total_weight <= 0:
        raise ValueError("The football and market weights must add up to a positive number.")
    football_weight /= total_weight
    market_weight /= total_weight

    teams = sorted(str(row["team"]) for row in rows)
    priors = prior_ratings(rows)
    football, football_hfa, football_diagnostics = solve_team_ratings(
        teams,
        football_observations(games),
        priors,
        FOOTBALL_RIDGE_STRENGTH,
    )
    market, market_hfa, market_diagnostics = solve_team_ratings(
        teams,
        market_observations(lines),
        priors,
        MARKET_RIDGE_STRENGTH,
    )
    final = centered(
        {
            team: (football_weight * football[team]) + (market_weight * market[team])
            for team in teams
        }
    )
    components = {
        team: {
            "football_rating": football[team],
            "market_rating": market[team],
            "rating": final[team],
            "market_gap": market[team] - football[team],
        }
        for team in teams
    }
    diagnostics = {
        "rating_system": "dual",
        "football_weight": round(football_weight, 4),
        "market_weight": round(market_weight, 4),
        "football_home_field": round(football_hfa, 3),
        "market_home_field": round(market_hfa, 3),
        "blended_home_field": round((football_weight * football_hfa) + (market_weight * market_hfa), 3),
        "production_home_field": HOME_FIELD_PRIOR,
        **{f"football_{key}": round(value, 3) for key, value in football_diagnostics.items()},
        **{f"market_{key}": round(value, 3) for key, value in market_diagnostics.items()},
    }
    return components, diagnostics

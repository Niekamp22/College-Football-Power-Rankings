from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


DEFAULT_COMPLETED_REVIEW_PATH = Path("output/reviews/completed_games_review_2026.csv")
DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_current.csv")
DEFAULT_OUTPUT_ROOT = Path("output/analytics")
MARGIN_STD_DEV = 16.0


EDGE_BUCKETS = [
    (0.0, 2.5, "0-2.5"),
    (2.5, 5.0, "2.5-5"),
    (5.0, 7.5, "5-7.5"),
    (7.5, 10.0, "7.5-10"),
    (10.0, 15.0, "10-15"),
    (15.0, math.inf, "15+"),
]

WIN_PROB_BUCKETS = [
    (0.50, 0.55, "50-55%"),
    (0.55, 0.60, "55-60%"),
    (0.60, 0.65, "60-65%"),
    (0.65, 0.70, "65-70%"),
    (0.70, 0.75, "70-75%"),
    (0.75, 0.80, "75-80%"),
    (0.80, 0.90, "80-90%"),
    (0.90, 1.01, "90%+"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build betting analytics summaries from completed game review data.")
    parser.add_argument("--completed-review", type=Path, default=DEFAULT_COMPLETED_REVIEW_PATH)
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS_PATH)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    extra_fields = sorted({key for row in rows for key in row.keys()} - set(fieldnames))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + extra_fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: Any, default: float = 0.0) -> float:
    if value in ("", None):
        return default
    try:
        if math.isnan(float(value)):
            return default
    except (TypeError, ValueError):
        return default
    return float(value)


def average(values: Iterable[float]) -> float:
    clean_values = [value for value in values if value is not None and not math.isnan(value)]
    return mean(clean_values) if clean_values else 0.0


def rate(values: Iterable[bool]) -> float:
    clean_values = list(values)
    return sum(clean_values) / len(clean_values) if clean_values else 0.0


def edge_bucket(value: float) -> str:
    for low, high, label in EDGE_BUCKETS:
        if low <= value < high:
            return label
    return "unknown"


def win_probability(margin: float) -> float:
    z_score = margin / MARGIN_STD_DEV
    return 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))


def probability_bucket(value: float) -> str:
    for low, high, label in WIN_PROB_BUCKETS:
        if low <= value < high:
            return label
    return "unknown"


def team_conference_lookup(ratings_rows: list[dict[str, Any]]) -> dict[str, str]:
    return {row.get("team", ""): row.get("conference", "") for row in ratings_rows if row.get("team")}


def edge_pick_context(row: dict[str, Any]) -> dict[str, Any]:
    edge_home = parse_float(row.get("model_edge_home_points"))
    abs_edge = abs(edge_home)
    pick_home = edge_home > 0
    pick_team = row.get("home_team") if pick_home else row.get("away_team")
    pick_site = "home" if pick_home else "away"
    pick_market_spread = parse_float(row.get("market_home_spread")) if pick_home else -parse_float(row.get("market_home_spread"))
    if pick_market_spread < 0:
        pick_role = "favorite"
    elif pick_market_spread > 0:
        pick_role = "underdog"
    else:
        pick_role = "pick'em"
    return {
        "pick_team": pick_team,
        "pick_site": "neutral" if str(row.get("neutral_site", "")).lower() == "true" else pick_site,
        "pick_role": pick_role,
        "abs_edge": abs_edge,
        "edge_bucket": edge_bucket(abs_edge),
        "edge_hit": row.get("edge_result") == "right_side",
    }


def build_edge_bucket_summary(completed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in completed_rows:
        context = edge_pick_context(row)
        rows.append({**row, **context})
    summary = []
    for label in [bucket[2] for bucket in EDGE_BUCKETS]:
        group = [row for row in rows if row["edge_bucket"] == label]
        summary.append(
            {
                "edge_bucket": label,
                "games": len(group),
                "edge_hit_rate": round(rate(row["edge_hit"] for row in group), 4),
                "model_better_than_market_rate": round(
                    rate(parse_float(row.get("absolute_model_error")) < parse_float(row.get("absolute_market_error")) for row in group),
                    4,
                ),
                "model_margin_mae": round(average(parse_float(row.get("absolute_model_error")) for row in group), 3),
                "market_margin_mae": round(average(parse_float(row.get("absolute_market_error")) for row in group), 3),
                "average_edge": round(average(row["abs_edge"] for row in group), 3),
            }
        )
    return summary


def summarize_group(rows: list[dict[str, Any]], group_field: str) -> list[dict[str, Any]]:
    output = []
    group_values = sorted({str(row.get(group_field, "")) for row in rows})
    for value in group_values:
        group = [row for row in rows if str(row.get(group_field, "")) == value]
        output.append(
            {
                group_field: value,
                "games": len(group),
                "edge_hit_rate": round(rate(row["edge_hit"] for row in group), 4),
                "model_better_than_market_rate": round(
                    rate(parse_float(row.get("absolute_model_error")) < parse_float(row.get("absolute_market_error")) for row in group),
                    4,
                ),
                "model_margin_mae": round(average(parse_float(row.get("absolute_model_error")) for row in group), 3),
                "market_margin_mae": round(average(parse_float(row.get("absolute_market_error")) for row in group), 3),
                "average_edge": round(average(row["abs_edge"] for row in group), 3),
            }
        )
    return output


def build_split_summary(completed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = [{**row, **edge_pick_context(row)} for row in completed_rows]
    rows: list[dict[str, Any]] = []
    for split_name, field in [
        ("Game Type", "game_type"),
        ("Pick Role", "pick_role"),
        ("Pick Site", "pick_site"),
        ("Week", "week_label"),
    ]:
        for summary in summarize_group(enriched, field):
            value = summary.pop(field)
            rows.append({"split": split_name, "value": value, **summary})
    return rows


def build_team_bias(completed_rows: list[dict[str, Any]], conferences: dict[str, str]) -> list[dict[str, Any]]:
    team_rows: list[dict[str, Any]] = []
    for row in completed_rows:
        actual_home_margin = parse_float(row.get("actual_home_margin"))
        model_home_margin = parse_float(row.get("model_home_margin"))
        market_home_spread = parse_float(row.get("market_home_spread"))
        model_edge_home = parse_float(row.get("model_edge_home_points"))

        for side in ("home", "away"):
            is_home = side == "home"
            team = row.get("home_team") if is_home else row.get("away_team")
            actual_margin = actual_home_margin if is_home else -actual_home_margin
            model_margin = model_home_margin if is_home else -model_home_margin
            market_spread = market_home_spread if is_home else -market_home_spread
            ats_margin = actual_margin + market_spread
            model_edge = model_edge_home if is_home else -model_edge_home
            team_rows.append(
                {
                    "team": team,
                    "conference": conferences.get(str(team), ""),
                    "game_type": row.get("game_type", ""),
                    "games": 1,
                    "ats_cover": ats_margin > 0,
                    "ats_margin": ats_margin,
                    "model_bias_margin": model_margin - actual_margin,
                    "model_edge_pick": model_edge > 0,
                    "model_edge_hit": model_edge > 0 and ats_margin > 0,
                    "model_error": parse_float(row.get("absolute_model_error")),
                    "market_error": parse_float(row.get("absolute_market_error")),
                }
            )

    output = []
    for team in sorted({row["team"] for row in team_rows}):
        group = [row for row in team_rows if row["team"] == team]
        edge_picks = [row for row in group if row["model_edge_pick"]]
        output.append(
            {
                "team": team,
                "conference": group[0]["conference"],
                "games": len(group),
                "ats_cover_rate": round(rate(row["ats_cover"] for row in group), 4),
                "average_ats_margin": round(average(row["ats_margin"] for row in group), 3),
                "average_model_bias_margin": round(average(row["model_bias_margin"] for row in group), 3),
                "model_edge_picks": len(edge_picks),
                "edge_pick_hit_rate": round(rate(row["model_edge_hit"] for row in edge_picks), 4),
                "model_margin_mae": round(average(row["model_error"] for row in group), 3),
                "market_margin_mae": round(average(row["market_error"] for row in group), 3),
            }
        )
    output.sort(key=lambda row: (abs(float(row["average_model_bias_margin"])), row["games"]), reverse=True)
    return output


def build_conference_summary(team_bias_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for conference in sorted({row["conference"] for row in team_bias_rows if row.get("conference")}):
        group = [row for row in team_bias_rows if row.get("conference") == conference]
        output.append(
            {
                "conference": conference,
                "teams": len(group),
                "team_games": sum(int(row["games"]) for row in group),
                "average_ats_cover_rate": round(average(float(row["ats_cover_rate"]) for row in group), 4),
                "average_model_bias_margin": round(average(float(row["average_model_bias_margin"]) for row in group), 3),
                "average_model_margin_mae": round(average(float(row["model_margin_mae"]) for row in group), 3),
                "average_market_margin_mae": round(average(float(row["market_margin_mae"]) for row in group), 3),
            }
        )
    output.sort(key=lambda row: row["average_model_margin_mae"], reverse=True)
    return output


def build_big_misses(completed_rows: list[dict[str, Any]], threshold: float = 20.0) -> list[dict[str, Any]]:
    output = []
    for row in completed_rows:
        model_error = parse_float(row.get("absolute_model_error"))
        if model_error < threshold:
            continue
        context = edge_pick_context(row)
        output.append(
            {
                "week_label": row.get("week_label", ""),
                "game_type": row.get("game_type", ""),
                "away_team": row.get("away_team", ""),
                "home_team": row.get("home_team", ""),
                "actual_home_margin": row.get("actual_home_margin", ""),
                "model_home_margin": row.get("model_home_margin", ""),
                "market_home_margin": row.get("market_home_margin", ""),
                "absolute_model_error": row.get("absolute_model_error", ""),
                "absolute_market_error": row.get("absolute_market_error", ""),
                "edge_bucket": context["edge_bucket"],
                "edge_pick_team": context["pick_team"],
                "edge_result": row.get("edge_result", ""),
            }
        )
    output.sort(key=lambda row: parse_float(row["absolute_model_error"]), reverse=True)
    return output


def build_market_disagreements(completed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in completed_rows:
        model_home_margin = parse_float(row.get("model_home_margin"))
        market_home_margin = parse_float(row.get("market_home_margin"))
        model_favorite = row.get("home_team") if model_home_margin >= 0 else row.get("away_team")
        market_favorite = row.get("home_team") if market_home_margin >= 0 else row.get("away_team")
        if model_favorite == market_favorite:
            continue
        output.append(
            {
                "week_label": row.get("week_label", ""),
                "game_type": row.get("game_type", ""),
                "away_team": row.get("away_team", ""),
                "home_team": row.get("home_team", ""),
                "model_favorite": model_favorite,
                "market_favorite": market_favorite,
                "winner_model_result": row.get("winner_model_result", ""),
                "winner_market_result": row.get("winner_market_result", ""),
                "model_home_margin": row.get("model_home_margin", ""),
                "market_home_margin": row.get("market_home_margin", ""),
                "actual_home_margin": row.get("actual_home_margin", ""),
                "absolute_model_error": row.get("absolute_model_error", ""),
                "absolute_market_error": row.get("absolute_market_error", ""),
            }
        )
    output.sort(key=lambda row: parse_float(row["absolute_model_error"]), reverse=True)
    return output


def build_probability_calibration(completed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for row in completed_rows:
        model_home_margin = parse_float(row.get("model_home_margin"))
        actual_home_margin = parse_float(row.get("actual_home_margin"))
        home_probability = win_probability(model_home_margin)
        picked_home = home_probability >= 0.5
        picked_probability = home_probability if picked_home else 1.0 - home_probability
        picked_won = actual_home_margin > 0 if picked_home else actual_home_margin < 0
        enriched.append(
            {
                "bucket": probability_bucket(picked_probability),
                "picked_probability": picked_probability,
                "picked_won": picked_won,
            }
        )

    output = []
    for _, _, label in WIN_PROB_BUCKETS:
        group = [row for row in enriched if row["bucket"] == label]
        output.append(
            {
                "win_probability_bucket": label,
                "games": len(group),
                "average_model_probability": round(average(row["picked_probability"] for row in group), 4),
                "actual_win_rate": round(rate(row["picked_won"] for row in group), 4),
                "calibration_gap": round(rate(row["picked_won"] for row in group) - average(row["picked_probability"] for row in group), 4)
                if group
                else 0.0,
            }
        )
    return output


def main() -> None:
    args = parse_args()
    completed_rows = load_csv(args.completed_review)
    ratings_rows = load_csv(args.ratings)
    conferences = team_conference_lookup(ratings_rows)

    edge_summary = build_edge_bucket_summary(completed_rows)
    split_summary = build_split_summary(completed_rows)
    team_bias = build_team_bias(completed_rows, conferences)
    conference_summary = build_conference_summary(team_bias)
    big_misses = build_big_misses(completed_rows)
    market_disagreements = build_market_disagreements(completed_rows)
    probability_calibration = build_probability_calibration(completed_rows)

    args.output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        f"edge_bucket_summary_{args.season}.csv": edge_summary,
        f"split_summary_{args.season}.csv": split_summary,
        f"team_bias_{args.season}.csv": team_bias,
        f"conference_summary_{args.season}.csv": conference_summary,
        f"big_misses_{args.season}.csv": big_misses,
        f"market_disagreements_{args.season}.csv": market_disagreements,
        f"probability_calibration_{args.season}.csv": probability_calibration,
    }
    for filename, rows in outputs.items():
        write_csv(args.output_root / filename, rows)
        print(f"Saved {filename} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

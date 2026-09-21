from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DEFAULT_OUTPUT = Path("output/refresh_status.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated public-app files before publishing them.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_csv(
    path: Path,
    required_columns: set[str],
    errors: list[str],
    stats: dict[str, object],
    minimum_rows: int = 1,
) -> pd.DataFrame:
    if not path.exists():
        errors.append(f"Missing required output: {path}")
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        errors.append(f"Could not read {path}: {exc}")
        return pd.DataFrame()
    stats[f"{path.stem}_rows"] = len(frame)
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        errors.append(f"{path} is missing columns: {', '.join(missing)}")
    if len(frame) < minimum_rows:
        errors.append(f"{path} has {len(frame)} rows; expected at least {minimum_rows}")
    return frame


def validate_projection_math(totals: pd.DataFrame, errors: list[str]) -> None:
    required = {"actual_wins", "remaining_expected_wins", "projected_wins", "schedule_games"}
    if totals.empty or not required.issubset(totals.columns):
        return
    numeric = totals[list(required)].apply(pd.to_numeric, errors="coerce")
    invalid_numbers = numeric.isna().any(axis=1)
    if invalid_numbers.any():
        errors.append(f"Win totals contain {int(invalid_numbers.sum())} rows with invalid numeric values")
    expected = numeric["actual_wins"] + numeric["remaining_expected_wins"]
    mismatches = (expected - numeric["projected_wins"]).abs() > 0.011
    if mismatches.any():
        errors.append(f"Win-total math failed for {int(mismatches.sum())} teams")
    outside_schedule = (numeric["projected_wins"] < 0) | (numeric["projected_wins"] > numeric["schedule_games"])
    if outside_schedule.any():
        errors.append(f"Projected wins fall outside the schedule for {int(outside_schedule.sum())} teams")


def validate_outputs(season: int) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, object] = {"season": season}

    ratings = read_csv(
        Path("output/cfbd_power_ratings_current.csv"),
        {"team", "rating", "football_rating", "market_rating", "record", "rating_confidence"},
        errors,
        stats,
        minimum_rows=120,
    )
    if not ratings.empty:
        duplicate_teams = ratings["team"].duplicated().sum()
        if duplicate_teams:
            errors.append(f"Ratings contain {int(duplicate_teams)} duplicate teams")
        invalid_ratings = pd.to_numeric(ratings["rating"], errors="coerce").isna().sum()
        if invalid_ratings:
            errors.append(f"Ratings contain {int(invalid_ratings)} invalid rating values")

    totals = read_csv(
        Path(f"output/projections/projected_win_totals_{season}.csv"),
        {
            "team",
            "actual_wins",
            "actual_losses",
            "remaining_expected_wins",
            "remaining_games",
            "projected_wins",
            "schedule_games",
        },
        errors,
        stats,
        minimum_rows=120,
    )
    validate_projection_math(totals, errors)

    projected_games = read_csv(
        Path(f"output/projections/projected_games_{season}.csv"),
        {"game_id", "team", "opponent", "display_week", "status", "projected_spread", "win_probability"},
        errors,
        stats,
        minimum_rows=500,
    )
    if not projected_games.empty and {"game_id", "team"}.issubset(projected_games.columns):
        duplicate_team_games = projected_games.duplicated(["game_id", "team"]).sum()
        if duplicate_team_games:
            errors.append(f"Projected games contain {int(duplicate_team_games)} duplicate team/game rows")
        stats["unique_projected_games"] = int(projected_games["game_id"].nunique())

    coverage = read_csv(
        Path(f"output/projections/schedule_coverage_{season}.csv"),
        {"team", "schedule_games", "missing_games", "status"},
        errors,
        stats,
        minimum_rows=120,
    )
    if not coverage.empty:
        incomplete = coverage[coverage["status"].eq("incomplete")]
        stats["incomplete_schedules"] = len(incomplete)
        if not incomplete.empty:
            warnings.append(
                f"{len(incomplete)} teams have incomplete schedules; forecasts remain published with an in-app warning"
            )

    completed = read_csv(
        Path(f"output/reviews/completed_games_review_{season}.csv"),
        {"display_week", "rating_source", "home_team", "away_team", "absolute_model_error"},
        errors,
        stats,
        minimum_rows=1,
    )
    if not completed.empty:
        stats["forward_graded_games"] = int(completed["rating_source"].astype(str).str.endswith("_snapshot").sum())
        stats["retrospective_games"] = int(completed["rating_source"].eq("current_retrospective").sum())

    odds = read_csv(
        Path("output/odds/ncaaf_game_odds_comparison.csv"),
        {"event_id", "display_week", "home_team", "away_team", "market_status", "captured_at_utc"},
        errors,
        stats,
        minimum_rows=1,
    )
    if not odds.empty:
        captured = pd.to_datetime(odds["captured_at_utc"], errors="coerce", utc=True).dropna()
        stats["odds_games"] = len(odds)
        stats["odds_last_captured_utc"] = captured.max().isoformat() if not captured.empty else None
        if captured.empty:
            warnings.append("No current odds capture timestamp was found")

    snapshots = sorted(Path(f"output/snapshots/{season}").glob("week_*_ratings.csv"))
    stats["rating_snapshots"] = len(snapshots)
    if not snapshots:
        errors.append(f"No frozen rating snapshot exists for {season}")
    else:
        stats["latest_rating_snapshot"] = snapshots[-1].name

    workbook = Path("output/power_ratings_master.xlsx")
    if not workbook.exists() or workbook.stat().st_size < 10_000:
        errors.append("Master Excel workbook is missing or unexpectedly small")
    else:
        stats["master_workbook_bytes"] = workbook.stat().st_size

    return {
        "status": "passed" if not errors else "failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def main() -> None:
    args = parse_args()
    report = validate_outputs(args.season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Public output validation: {report['status'].upper()}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    print(f"Wrote validation report to {args.output}")
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

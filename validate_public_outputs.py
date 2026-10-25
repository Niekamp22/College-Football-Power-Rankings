from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import hashlib

import pandas as pd


DEFAULT_OUTPUT = Path("output/refresh_status.json")


def validate_poll(season: int, ratings: pd.DataFrame, errors: list[str], stats: dict[str, object]) -> None:
    root = Path("output/polls")
    poll = read_csv(root / f"joshs_poll_{season}.csv", {
        "rank", "team", "record", "games_played", "wins", "losses", "through_week", "resume_score", "power_score",
        "poll_score", "resume_contribution", "power_contribution", "resume_raw", "win_credits", "loss_penalties",
    }, errors, stats, minimum_rows=120)
    details = read_csv(root / f"joshs_poll_games_{season}.csv", {
        "game_id", "team", "opponent", "result", "resume_points", "win_credit", "loss_penalty",
    }, errors, stats, minimum_rows=1)
    if poll.empty or not {"rank", "poll_score", "resume_score", "power_score", "team", "resume_raw", "games_played",
                          "wins", "losses", "win_credits", "loss_penalties", "resume_contribution", "power_contribution"}.issubset(poll.columns):
        return
    if poll["team"].duplicated().any() or set(poll["team"]) != set(ratings["team"]):
        errors.append("Josh's Poll team coverage does not match power ratings")
    ranked = poll[poll["rank"].notna()]
    if sorted(ranked["rank"].tolist()) != list(range(1, len(ranked) + 1)):
        errors.append("Josh's Poll ranks are not consecutive and unique")
    score_columns = ["resume_score", "power_score", "poll_score"]
    numeric = ranked[score_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or (numeric < -1e-6).any().any() or (numeric > 100.000001).any().any():
        errors.append("Josh's Poll has missing or out-of-range scores")
    if ((ranked["poll_score"] - 0.7 * ranked["resume_score"] - 0.3 * ranked["power_score"]).abs() > 0.00001).any():
        errors.append("Josh's Poll 70/30 blend does not reconcile")
    if ((ranked["resume_contribution"] - 0.7 * ranked["resume_score"]).abs() > 0.00001).any() or ((ranked["power_contribution"] - 0.3 * ranked["power_score"]).abs() > 0.00001).any():
        errors.append("Josh's Poll score contributions do not reconcile")
    if not details.empty and {"game_id", "team", "resume_points", "win_credit", "loss_penalty", "result"}.issubset(details.columns):
        if details.duplicated(["game_id", "team"]).any():
            errors.append("Josh's Poll contains duplicate team/game credits")
        totals = details.groupby("team")["resume_points"].sum()
        expected = poll["team"].map(totals).fillna(0.0)
        if ((expected - poll["resume_raw"]).abs() > 0.0001).any():
            errors.append("Josh's Poll game credits do not reconcile to resume totals")
        if ((poll["resume_raw"] - poll["win_credits"] + poll["loss_penalties"]).abs() > 0.00001).any():
            errors.append("Josh's Poll win credits and loss deductions do not reconcile")
        counts = details.groupby("team").size()
        victories = details[details["result"].eq("W")].groupby("team").size()
        defeats = details[details["result"].eq("L")].groupby("team").size()
        for column, series in (("games_played", counts), ("wins", victories), ("losses", defeats)):
            if (poll[column] != poll["team"].map(series).fillna(0)).any():
                errors.append(f"Josh's Poll {column} does not reconcile to game detail")
        if ((poll["games_played"] > 0) != poll["rank"].notna()).any():
            errors.append("Josh's Poll has an incorrect played/unranked status")
    metadata_path = root / str(season) / "latest_metadata.json"
    if not metadata_path.exists():
        errors.append("Josh's Poll metadata is missing")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        rating_hash = hashlib.sha256(Path("output/cfbd_power_ratings_current.csv").read_bytes()).hexdigest()
        if metadata.get("ratings_sha256") != rating_hash:
            errors.append("Josh's Poll is stale relative to current power ratings")
        games_path = Path(f"data/cfbd/raw/{season}/games.json")
        if games_path.exists() and metadata.get("games_sha256") != hashlib.sha256(games_path.read_bytes()).hexdigest():
            errors.append("Josh's Poll is stale relative to current game results")
    stats["joshs_poll_through_week"] = int(poll["through_week"].max())
    stats["joshs_poll_ranked_teams"] = len(ranked)


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

    if not ratings.empty:
        validate_poll(season, ratings, errors, stats)

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

    best_bets = read_csv(
        Path(f"output/best_bets/best_bet_ledger_{season}.csv"),
        {
            "display_week",
            "selection_rank",
            "event_id",
            "pick_team",
            "locked_spread",
            "locked_price",
            "status",
            "ats_result",
            "units",
            "cumulative_units",
        },
        errors,
        stats,
        minimum_rows=1,
    )
    if not best_bets.empty:
        duplicate_picks = best_bets.duplicated(["display_week", "event_id"]).sum()
        if duplicate_picks:
            errors.append(f"Best-bet ledger contains {int(duplicate_picks)} duplicate week/event picks")
        week_counts = best_bets.groupby("display_week").size()
        if week_counts.gt(6).any():
            errors.append("Best-bet ledger contains more than six picks in a week")
        valid_statuses = {"pending", "graded"}
        invalid_statuses = set(best_bets["status"].dropna().astype(str)) - valid_statuses
        if invalid_statuses:
            errors.append(f"Best-bet ledger contains invalid statuses: {', '.join(sorted(invalid_statuses))}")
        stats["best_bets_graded"] = int(best_bets["status"].eq("graded").sum())
        stats["best_bets_pending"] = int(best_bets["status"].eq("pending").sum())

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

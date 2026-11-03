from __future__ import annotations

import math
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from app_data import load_csv, load_json


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_current.csv")
DEFAULT_BACKTEST_PATH = Path("output/backtests/weekly_backtest_2025_regular.csv")
DEFAULT_EXCEL_PATH = Path("output/power_ratings_master.xlsx")
DEFAULT_WIN_TOTALS_PATH = Path("output/projections/projected_win_totals_2026.csv")
DEFAULT_PROJECTED_GAMES_PATH = Path("output/projections/projected_games_2026.csv")
DEFAULT_SCHEDULE_COVERAGE_PATH = Path("output/projections/schedule_coverage_2026.csv")
DEFAULT_ODDS_COMPARISON_PATH = Path("output/odds/ncaaf_game_odds_comparison.csv")
DEFAULT_ODDS_HISTORY_PATH = Path("output/odds/odds_history.csv")
DEFAULT_CLV_SUMMARY_PATH = Path("output/odds/clv_summary.csv")
DEFAULT_WEEKLY_RESULTS_REVIEW_PATH = Path("output/reviews/weekly_results_review_2026.csv")
DEFAULT_COMPLETED_GAMES_REVIEW_PATH = Path("output/reviews/completed_games_review_2026.csv")
DEFAULT_EDGE_BUCKET_SUMMARY_PATH = Path("output/analytics/edge_bucket_summary_2026.csv")
DEFAULT_SPLIT_SUMMARY_PATH = Path("output/analytics/split_summary_2026.csv")
DEFAULT_TEAM_BIAS_PATH = Path("output/analytics/team_bias_2026.csv")
DEFAULT_CONFERENCE_SUMMARY_PATH = Path("output/analytics/conference_summary_2026.csv")
DEFAULT_BIG_MISSES_PATH = Path("output/analytics/big_misses_2026.csv")
DEFAULT_MARKET_DISAGREEMENTS_PATH = Path("output/analytics/market_disagreements_2026.csv")
DEFAULT_PROBABILITY_CALIBRATION_PATH = Path("output/analytics/probability_calibration_2026.csv")
DEFAULT_ATS_VALIDATION_PATH = Path("output/analytics/ats_model_validation.csv")
DEFAULT_MARGIN_CHALLENGER_PATH = Path("output/analytics/margin_challenger_validation.csv")
DEFAULT_REFRESH_STATUS_PATH = Path("output/refresh_status.json")
DEFAULT_BEST_BETS_PATH = Path("output/best_bets/best_bet_ledger_2026.csv")


def format_eastern_time(value: object, compact: bool = True) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "TBD"
    eastern = timestamp.tz_convert("America/New_York")
    formatted = eastern.strftime("%a %b %d, %I:%M %p ET")
    return formatted.replace(" 0", " ") if compact else formatted


def format_percent(value: object, decimals: int = 1) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "N/A" if pd.isna(numeric) else f"{float(numeric) * 100:.{decimals}f}%"


def friendly_book_name(value: object) -> str:
    names = {
        "betmgm": "BetMGM",
        "betrivers": "BetRivers",
        "betonlineag": "BetOnline",
        "betus": "BetUS",
        "draftkings": "DraftKings",
        "fanduel": "FanDuel",
        "lowvig": "LowVig",
        "mybookieag": "MyBookie",
    }
    raw = str(value or "").strip()
    return names.get(raw.lower(), raw.replace("_", " ").title())


def is_frozen_rating_source(value: object) -> bool:
    return str(value).startswith("week_") and str(value).endswith("_snapshot")


def default_week_index(board: pd.DataFrame, now: pd.Timestamp | None = None) -> int:
    """Choose the first week with an unplayed game, falling back to the latest week."""
    if board.empty or "display_week" not in board.columns:
        return 0
    weeks = sorted(int(week) for week in board["display_week"].dropna().unique())
    if not weeks:
        return 0
    current_time = now if now is not None else pd.Timestamp.now(tz="UTC")
    if current_time.tzinfo is None:
        current_time = current_time.tz_localize("UTC")
    starts = pd.to_datetime(board.get("start_date"), errors="coerce", utc=True)
    completed = board.get("status", pd.Series("", index=board.index)).astype(str).str.lower().eq("final")
    upcoming = board[(~completed) & (starts >= current_time)]
    target_week = int(upcoming["display_week"].min()) if not upcoming.empty else max(weeks)
    return weeks.index(target_week)


def summarize_completed_games(games: pd.DataFrame) -> pd.DataFrame:
    if games.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for display_week, group in games.groupby("display_week", dropna=True):
        market = group[group["absolute_market_error"].notna()]
        edge = group[group["edge_result"].isin(["right_side", "wrong_side"])]
        rows.append(
            {
                "week_label": f"Week {int(display_week)}",
                "games": len(group),
                "games_with_market_line": len(market),
                "model_margin_mae": group["absolute_model_error"].mean(),
                "market_margin_mae": market["absolute_market_error"].mean() if not market.empty else pd.NA,
                "model_winner_accuracy": group["winner_model_result"].eq("correct").mean(),
                "market_winner_accuracy": market["winner_market_result"].eq("correct").mean() if not market.empty else pd.NA,
                "edge_right_side_rate": edge["edge_result"].eq("right_side").mean() if not edge.empty else pd.NA,
            }
        )
    return pd.DataFrame(rows)


def latest_snapshot_status(snapshot_root: Path = Path("output/snapshots/2026")) -> tuple[str, str]:
    metadata_paths = sorted(snapshot_root.glob("week_*_metadata.json"))
    if not metadata_paths:
        return "No snapshot", "Refresh time unavailable"
    metadata = load_json(metadata_paths[-1])
    week = metadata.get("prediction_week", "?")
    refreshed = format_eastern_time(metadata.get("created_at_utc"))
    return f"Ratings prepared for Week {week}", f"Updated {refreshed}"


def load_refresh_status(path: Path = DEFAULT_REFRESH_STATUS_PATH) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except (json.JSONDecodeError, OSError):
        return {}


def win_probability(spread: float, margin_std_dev: float = 16.0) -> float:
    z_score = spread / margin_std_dev
    return 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))


def site_adjusted_spread(base_spread: float, site: str, home_field_advantage: float = 2.5) -> float:
    if site == "Team A Home":
        return base_spread + home_field_advantage
    if site == "Team B Home":
        return base_spread - home_field_advantage
    return base_spread


def add_week_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    with_display = df.copy()
    if "display_week" not in with_display.columns:
        with_display["display_week"] = with_display["week"]
    with_display["display_week"] = pd.to_numeric(with_display["display_week"], errors="coerce").astype("Int64")
    if "week_label" not in with_display.columns:
        with_display["week_label"] = with_display["display_week"].map(lambda week: f"Week {int(week)}" if pd.notna(week) else "")
    return with_display


def add_game_type_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    typed = df.copy()
    if "game_type" not in typed.columns:
        typed["game_type"] = typed.apply(
            lambda row: "FCS involved"
            if "fcs" in str(row.get("opponent_classification", "")).lower()
            or "fcs" in str(row.get("home_classification", "")).lower()
            or "fcs" in str(row.get("away_classification", "")).lower()
            or "FCS baseline" in str(row.get("opponent", ""))
            else "FBS vs FBS",
            axis=1,
        )
    return typed


def team_watchlist_label(row: pd.Series) -> str:
    flags: list[str] = []
    cover_margin = pd.to_numeric(pd.Series([row.get("avg_cover_margin")]), errors="coerce").iloc[0]
    if pd.notna(cover_margin) and cover_margin <= -20:
        flags.append("Market miss")
    fbs_record = str(row.get("fbs_record", ""))
    if fbs_record == "0-0":
        flags.append("FCS-only profile")
    return ", ".join(flags)


def summarize_team_betting(team_games: pd.DataFrame) -> pd.DataFrame:
    if team_games.empty:
        return pd.DataFrame()

    summary_rows: list[dict[str, object]] = []
    for team, group in team_games.groupby("team"):
        ats_decisions = group[group["ats_result"] != "push"]
        edge_picks = group[group["model_edge_pick"]]
        summary_rows.append(
            {
                "team": team,
                "games": len(group),
                "ats_decisions": len(ats_decisions),
                "ats_covers": int(ats_decisions["ats_result"].eq("cover").sum()),
                "ats_cover_rate": ats_decisions["ats_result"].eq("cover").mean() if not ats_decisions.empty else pd.NA,
                "avg_ats_margin": group["ats_margin"].mean(),
                "model_winner_picks": int(group["model_winner_pick"].sum()),
                "model_winner_accuracy": group["model_winner_hit"].mean(),
                "model_edge_picks": len(edge_picks),
                "edge_pick_hits": int(edge_picks["model_edge_hit"].sum()),
                "edge_pick_hit_rate": edge_picks["model_edge_hit"].mean() if not edge_picks.empty else pd.NA,
                "avg_edge_when_picked": edge_picks["model_edge"].mean() if not edge_picks.empty else pd.NA,
                "avg_model_error": group["absolute_model_error"].mean(),
                "avg_market_error": group["absolute_market_error"].mean(),
            }
        )

    team_summary = pd.DataFrame(summary_rows).sort_values(["model_edge_picks", "edge_pick_hit_rate"], ascending=[False, False])
    return team_summary


def build_team_betting_summary(completed_games: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if completed_games.empty:
        return pd.DataFrame(), pd.DataFrame()

    games = add_game_type_column(add_week_display_columns(completed_games))
    numeric_columns = [
        "display_week",
        "away_points",
        "home_points",
        "actual_home_margin",
        "model_home_margin",
        "market_home_margin",
        "market_home_spread",
        "absolute_model_error",
        "absolute_market_error",
        "model_edge_home_points",
    ]
    for column in numeric_columns:
        if column in games.columns:
            games[column] = pd.to_numeric(games[column], errors="coerce")

    team_rows: list[dict[str, object]] = []
    for _, game in games.iterrows():
        if pd.isna(game.get("actual_home_margin")) or pd.isna(game.get("market_home_spread")):
            continue

        for side in ("home", "away"):
            is_home = side == "home"
            team = game.get("home_team") if is_home else game.get("away_team")
            opponent = game.get("away_team") if is_home else game.get("home_team")
            points_for = game.get("home_points") if is_home else game.get("away_points")
            points_against = game.get("away_points") if is_home else game.get("home_points")
            actual_margin = game.get("actual_home_margin") if is_home else -game.get("actual_home_margin")
            model_margin = game.get("model_home_margin") if is_home else -game.get("model_home_margin")
            market_margin = game.get("market_home_margin") if is_home else -game.get("market_home_margin")
            market_spread = game.get("market_home_spread") if is_home else -game.get("market_home_spread")
            model_edge = model_margin - market_margin
            ats_margin = actual_margin + market_spread
            model_winner_pick = model_margin > 0
            actual_win = actual_margin > 0
            edge_pick = model_edge > 0

            team_rows.append(
                {
                    "week_label": game.get("week_label", ""),
                    "display_week": game.get("display_week"),
                    "start_date": game.get("start_date", ""),
                    "team": team,
                    "opponent": opponent,
                    "game_type": game.get("game_type", ""),
                    "site": "home" if is_home else "away",
                    "points_for": points_for,
                    "points_against": points_against,
                    "actual_margin": actual_margin,
                    "market_spread": market_spread,
                    "ats_margin": ats_margin,
                    "ats_result": "cover" if ats_margin > 0 else "no_cover" if ats_margin < 0 else "push",
                    "model_margin": model_margin,
                    "model_winner_pick": model_winner_pick,
                    "model_winner_hit": model_winner_pick == actual_win,
                    "model_edge": model_edge,
                    "model_edge_pick": edge_pick,
                    "model_edge_hit": edge_pick and ats_margin > 0,
                    "absolute_model_error": game.get("absolute_model_error"),
                    "absolute_market_error": game.get("absolute_market_error"),
                }
            )

    team_games = pd.DataFrame(team_rows)
    team_summary = summarize_team_betting(team_games)
    return team_summary, team_games


def render_missing_state(path: Path, label: str) -> None:
    st.warning(f"{label} was not found at `{path}`.")

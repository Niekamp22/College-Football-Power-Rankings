from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st


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


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


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


def build_podcast_shortlist(
    odds: pd.DataFrame,
    ratings: pd.DataFrame,
    week: int | None = None,
    min_edge: float = 3.0,
    max_edge: float = 8.5,
    min_books: int = 4,
) -> pd.DataFrame:
    """Rank well-supported candidates without claiming a validated ATS advantage."""
    if odds.empty or ratings.empty:
        return pd.DataFrame()

    board = odds.copy()
    for column in [
        "display_week",
        "book_count",
        "model_home_spread",
        "market_home_margin",
        "edge_home_points",
        "absolute_edge_points",
        "selected_best_spread",
        "selected_best_price",
        "line_shopping_value",
    ]:
        if column in board.columns:
            board[column] = pd.to_numeric(board[column], errors="coerce")

    board = board[
        board["market_home_margin"].notna()
        & board["selected_best_spread"].notna()
        & board["selected_best_price"].notna()
        & board["absolute_edge_points"].between(min_edge, max_edge, inclusive="both")
        & (board["book_count"].fillna(0) >= min_books)
        & (board["selected_best_price"] >= -120)
        & (board["market_home_margin"].abs() <= 14.0)
        & board["game_type"].eq("FBS vs FBS")
        & board["betting_status"].eq("Standard")
    ].copy()
    if board.empty:
        return pd.DataFrame()

    selected_week = week if week is not None else int(board["display_week"].max())
    board = board[board["display_week"] == selected_week]
    rating_lookup = ratings.set_index("team")
    confidence_values = {"High": 1.0, "Medium": 0.65, "Low": 0.3, "Legacy": 0.4}
    rows: list[dict[str, object]] = []

    for _, game in board.iterrows():
        home_team = str(game["home_team"])
        away_team = str(game["away_team"])
        if home_team not in rating_lookup.index or away_team not in rating_lookup.index:
            continue

        home = rating_lookup.loc[home_team]
        away = rating_lookup.loc[away_team]
        neutral_site = str(game.get("neutral_site", "")).strip().lower() in {"true", "1", "yes"}
        home_field = 0.0 if neutral_site else 2.5
        market_margin = float(game["market_home_margin"])
        direction = 1.0 if float(game["edge_home_points"]) >= 0 else -1.0
        football_edge = (
            float(home["football_rating"]) - float(away["football_rating"]) + home_field - market_margin
        )
        market_component_edge = (
            float(home["market_rating"]) - float(away["market_rating"]) + home_field - market_margin
        )
        components_agree = direction * football_edge > 0 and direction * market_component_edge > 0
        if not components_agree:
            continue

        home_confidence = confidence_values.get(str(home.get("rating_confidence", "")), 0.4)
        away_confidence = confidence_values.get(str(away.get("rating_confidence", "")), 0.4)
        if min(home_confidence, away_confidence) < confidence_values["Medium"]:
            continue
        confidence_score = (home_confidence + away_confidence) / 2
        edge = float(game["absolute_edge_points"])
        edge_quality = max(0.0, 1.0 - abs(edge - 5.5) / 5.5)
        liquidity_score = min(float(game["book_count"]) / 8.0, 1.0)
        raw_shopping_value = game.get("line_shopping_value")
        shopping_value = float(raw_shopping_value) if pd.notna(raw_shopping_value) else 0.0
        shopping_score = min(max(shopping_value, 0.0) / 1.5, 1.0)
        max_market_gap = max(abs(float(home["market_gap"])), abs(float(away["market_gap"])))
        if max_market_gap >= 10.0:
            continue
        model_fair_line = (
            float(game["model_home_spread"])
            if str(game["edge_side"]) == home_team
            else -float(game["model_home_spread"])
        )
        candidate_score = (
            30.0 * edge_quality
            + 25.0
            + 15.0 * liquidity_score
            + 10.0 * shopping_score
            + 20.0 * confidence_score
        )
        caution = "Confirm injuries, weather, and the line before locking the pick."
        reasoning = (
            f"The model's fair line is {game['edge_side']} {model_fair_line:+.1f}, compared with the best available "
            f"{float(game['selected_best_spread']):+.1f}. The independent football rating and market-rating component "
            f"both support {game['edge_side']} against the consensus line. The price is available across "
            f"{int(float(game['book_count']))} tracked books, and line shopping improves the consensus spread by "
            f"{shopping_value:.2f} points."
        )

        rows.append(
            {
                "Week": f"Week {selected_week}",
                "Kickoff": game.get("commence_time", ""),
                "Matchup": f"{away_team} at {home_team}",
                "Model Lean": str(game["edge_side"]),
                "Model Fair Line": model_fair_line,
                "Best Line": float(game["selected_best_spread"]),
                "Price": int(float(game["selected_best_price"])),
                "Book": str(game.get("selected_best_book", "")),
                "Model Edge": edge,
                "Books": int(float(game["book_count"])),
                "Line Shopping Gain": shopping_value,
                "Candidate Score": round(candidate_score, 1),
                "Reasoning": reasoning,
                "Caution": caution,
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Candidate Score", "Model Edge"], ascending=[False, False]).reset_index(drop=True)


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


def main() -> None:
    st.set_page_config(
        page_title="College Football Power Ratings",
        page_icon="🏈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.title("College Football Power Ratings")
    st.caption("Market-calibrated college football power numbers with matchup and backtest views.")

    ratings_default = str(DEFAULT_RATINGS_PATH)
    backtest_default = str(DEFAULT_BACKTEST_PATH)
    win_totals_default = str(DEFAULT_WIN_TOTALS_PATH)
    projected_games_default = str(DEFAULT_PROJECTED_GAMES_PATH)
    schedule_coverage_default = str(DEFAULT_SCHEDULE_COVERAGE_PATH)
    odds_default = str(DEFAULT_ODDS_COMPARISON_PATH)
    weekly_review_default = str(DEFAULT_WEEKLY_RESULTS_REVIEW_PATH)
    completed_review_default = str(DEFAULT_COMPLETED_GAMES_REVIEW_PATH)
    edge_bucket_default = str(DEFAULT_EDGE_BUCKET_SUMMARY_PATH)
    split_summary_default = str(DEFAULT_SPLIT_SUMMARY_PATH)
    team_bias_default = str(DEFAULT_TEAM_BIAS_PATH)
    conference_summary_default = str(DEFAULT_CONFERENCE_SUMMARY_PATH)
    big_misses_default = str(DEFAULT_BIG_MISSES_PATH)
    market_disagreements_default = str(DEFAULT_MARKET_DISAGREEMENTS_PATH)
    probability_calibration_default = str(DEFAULT_PROBABILITY_CALIBRATION_PATH)

    ratings_path = ratings_default
    backtest_path = backtest_default
    win_totals_path = win_totals_default
    projected_games_path = projected_games_default
    schedule_coverage_path = schedule_coverage_default
    odds_path = odds_default
    weekly_review_path = weekly_review_default
    completed_review_path = completed_review_default
    ratings = load_csv(DEFAULT_RATINGS_PATH)
    backtest = load_csv(DEFAULT_BACKTEST_PATH)
    win_totals = load_csv(DEFAULT_WIN_TOTALS_PATH)
    projected_games = load_csv(DEFAULT_PROJECTED_GAMES_PATH)
    schedule_coverage = load_csv(DEFAULT_SCHEDULE_COVERAGE_PATH)
    odds = load_csv(DEFAULT_ODDS_COMPARISON_PATH)
    odds_history = load_csv(DEFAULT_ODDS_HISTORY_PATH)
    clv_summary = load_csv(DEFAULT_CLV_SUMMARY_PATH)
    weekly_review = load_csv(DEFAULT_WEEKLY_RESULTS_REVIEW_PATH)
    completed_review = load_csv(DEFAULT_COMPLETED_GAMES_REVIEW_PATH)
    edge_bucket_summary = load_csv(Path(edge_bucket_default))
    split_summary = load_csv(Path(split_summary_default))
    team_bias = load_csv(Path(team_bias_default))
    conference_summary = load_csv(Path(conference_summary_default))
    big_misses = load_csv(Path(big_misses_default))
    market_disagreements = load_csv(Path(market_disagreements_default))
    probability_calibration = load_csv(Path(probability_calibration_default))
    ats_validation = load_csv(DEFAULT_ATS_VALIDATION_PATH)
    margin_challenger_validation = load_csv(DEFAULT_MARGIN_CHALLENGER_PATH)

    st.sidebar.header("2026 Power Ratings")
    st.sidebar.caption("The app automatically uses the latest published model data.")
    if DEFAULT_EXCEL_PATH.exists():
        st.sidebar.download_button(
            "Download full Excel workbook",
            data=DEFAULT_EXCEL_PATH.read_bytes(),
            file_name=DEFAULT_EXCEL_PATH.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    st.sidebar.caption("Open the sidebar whenever you need the workbook. No file setup is required.")

    if ratings.empty:
        render_missing_state(Path(ratings_path), "Ratings file")
        st.info("The latest published model data is unavailable. Please try again after the next refresh.")
        st.stop()

    ratings = ratings.sort_values("rating", ascending=False).reset_index(drop=True)
    ratings.index = ratings.index + 1
    if "football_rating" not in ratings.columns:
        ratings["football_rating"] = ratings["rating"]
    if "market_rating" not in ratings.columns:
        ratings["market_rating"] = ratings["rating"]
    if "market_gap" not in ratings.columns:
        ratings["market_gap"] = ratings["market_rating"] - ratings["football_rating"]
    if "rating_confidence" not in ratings.columns:
        ratings["rating_confidence"] = "Legacy"

    top_row = ratings.iloc[0]
    st.markdown(
        f"""
        <div style="padding: 1rem 1.2rem; border-radius: 18px; background: linear-gradient(135deg, #14324a, #b6461d); color: white; margin-bottom: 1rem;">
          <div style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.12em; opacity: 0.85;">Current No. 1</div>
          <div style="font-size: 2rem; font-weight: 700;">{top_row['team']}</div>
          <div style="font-size: 1rem; opacity: 0.92;">Final {top_row['rating']:.2f} | Football {top_row['football_rating']:.2f} | Market {top_row['market_rating']:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rankings_tab, matchup_tab, weekly_tab, win_totals_tab, odds_tab, line_history_tab, team_betting_tab, analytics_tab, review_tab, backtest_tab = st.tabs(
        [
            "Rankings",
            "Matchup",
            "Games",
            "Win Totals",
            "Odds",
            "Line Tracking",
            "Team Trends",
            "Model Analysis",
            "Results",
            "Validation",
        ]
    )

    with rankings_tab:
        st.caption("Final Rating blends 60% independent football strength with 40% market-implied strength. Market Gap is market minus football.")
        conferences = ["All conferences"] + sorted(ratings["conference"].dropna().astype(str).unique().tolist())
        selected_conference = st.selectbox("Conference", conferences, index=0)
        search_term = st.text_input("Team search", placeholder="Start typing a team name")

        filtered = ratings.copy()
        filtered["watchlist"] = filtered.apply(team_watchlist_label, axis=1)
        watchlist_only = st.checkbox("Show watchlist teams only", value=False)
        if selected_conference != "All conferences":
            filtered = filtered[filtered["conference"] == selected_conference]
        if search_term:
            filtered = filtered[filtered["team"].str.contains(search_term, case=False, na=False)]
        if watchlist_only:
            filtered = filtered[filtered["watchlist"] != ""]

        show_components = st.checkbox("Show rating components", value=False)
        display_columns = ["team", "conference", "record", "rating", "rating_confidence"]
        display_labels = ["Team", "Conference", "Record", "Rating", "Confidence"]
        if show_components:
            display_columns += ["football_rating", "market_rating", "market_gap", "watchlist"]
            display_labels += ["Football", "Market", "Market Gap", "Watchlist"]

        display = filtered[display_columns].copy()
        display.insert(0, "rank", filtered.index)
        display.columns = ["Rank"] + display_labels
        st.dataframe(display, width="stretch", hide_index=True, height=620)

    with matchup_tab:
        team_names = ratings["team"].astype(str).tolist()
        col1, col2, col3 = st.columns(3)
        with col1:
            team_a_name = st.selectbox("Team A", team_names, index=0)
        with col2:
            team_b_name = st.selectbox("Team B", team_names, index=1 if len(team_names) > 1 else 0)
        with col3:
            game_site = st.selectbox("Game Site", ["Neutral", "Team A Home", "Team B Home"], index=0)

        team_a = ratings[ratings["team"] == team_a_name].iloc[0]
        team_b = ratings[ratings["team"] == team_b_name].iloc[0]
        base_spread = float(team_a["rating"]) - float(team_b["rating"])
        spread = site_adjusted_spread(base_spread, game_site)
        team_a_prob = win_probability(spread)

        metric1, metric2, metric3 = st.columns(3)
        favorite_label = f"{team_a_name} -{abs(spread):.1f}" if spread >= 0 else f"{team_b_name} -{abs(spread):.1f}"
        metric1.metric("Projected Spread", favorite_label)
        metric2.metric(f"{team_a_name} Win %", f"{team_a_prob * 100:.1f}%")
        metric3.metric(f"{team_b_name} Win %", f"{(1 - team_a_prob) * 100:.1f}%")
        st.caption(f"Site setting: {game_site}")

        comparison = pd.DataFrame(
            [
                {
                    "Team": team_a_name,
                    "Rating": float(team_a["rating"]),
                    "Football Rating": float(team_a["football_rating"]),
                    "Market Rating": float(team_a["market_rating"]),
                    "Market Gap": float(team_a["market_gap"]),
                    "Confidence": team_a["rating_confidence"],
                    "Record": team_a["record"],
                    "Efficiency": float(team_a["efficiency_score"]),
                    "Market": float(team_a["market_score"]),
                    "Schedule": float(team_a["schedule_score"]),
                },
                {
                    "Team": team_b_name,
                    "Rating": float(team_b["rating"]),
                    "Football Rating": float(team_b["football_rating"]),
                    "Market Rating": float(team_b["market_rating"]),
                    "Market Gap": float(team_b["market_gap"]),
                    "Confidence": team_b["rating_confidence"],
                    "Record": team_b["record"],
                    "Efficiency": float(team_b["efficiency_score"]),
                    "Market": float(team_b["market_score"]),
                    "Schedule": float(team_b["schedule_score"]),
                },
            ]
        )
        st.dataframe(comparison, width="stretch", hide_index=True)

    with weekly_tab:
        if projected_games.empty:
            render_missing_state(Path(projected_games_path), "Projected games file")
        else:
            weekly_board = add_game_type_column(add_week_display_columns(projected_games))
            weekly_board["week"] = weekly_board["week"].astype(int)
            available_weeks = sorted(int(week) for week in weekly_board["display_week"].dropna().unique())
            week_options = {f"Week {week}": week for week in available_weeks}
            game_type_options = ["All"] + sorted(weekly_board["game_type"].dropna().astype(str).unique().tolist())
            filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
            with filter_col1:
                selected_week_label = st.selectbox("Week", list(week_options), index=0, key="weekly_matchup_week")
                selected_week = week_options[selected_week_label]
            with filter_col2:
                selected_game_type = st.selectbox("Game Type", game_type_options, index=0, key="weekly_game_type")
            with filter_col3:
                matchup_search = st.text_input(
                    "Search weekly matchups",
                    placeholder="Search by team, opponent, or favorite",
                    key="weekly_matchup_search",
                ).strip().lower()
            board = weekly_board[weekly_board["display_week"] == selected_week].copy()
            board = board[board["site"].isin(["home", "neutral"])].copy()
            if selected_game_type != "All":
                board = board[board["game_type"] == selected_game_type]

            board["matchup"] = board.apply(
                lambda row: f"{row['opponent']} vs {row['team']}" if row["site"] == "neutral" else f"{row['opponent']} at {row['team']}",
                axis=1,
            )
            board["line"] = board.apply(
                lambda row: f"{row['favorite']} -{float(row['favorite_spread']):.1f}",
                axis=1,
            )
            board["home_team"] = board["team"]
            board["away_team"] = board["opponent"]
            board.loc[board["site"] == "neutral", "home_team"] = ""
            board.loc[board["site"] == "neutral", "away_team"] = ""

            if matchup_search:
                board = board[
                    board.apply(
                        lambda row: matchup_search in str(row["matchup"]).lower()
                        or matchup_search in str(row["favorite"]).lower()
                        or matchup_search in str(row["team"]).lower()
                        or matchup_search in str(row["opponent"]).lower(),
                        axis=1,
                    )
                ]

            display = board[
                ["week_label", "matchup", "game_type", "site", "line", "win_probability", "team_rating", "opponent_rating"]
            ].copy()
            display.columns = [
                "Week",
                "Matchup",
                "Game Type",
                "Site",
                "Projected Line",
                "Home/Listed Team Win %",
                "Listed Team Rating",
                "Opponent Rating",
            ]
            display["Home/Listed Team Win %"] = display["Home/Listed Team Win %"].map(lambda value: f"{float(value) * 100:.1f}%")
            st.dataframe(display, width="stretch", hide_index=True, height=520)

    with win_totals_tab:
        if win_totals.empty:
            render_missing_state(Path(win_totals_path), "Projected win totals file")
        else:
            if not schedule_coverage.empty and "status" in schedule_coverage.columns:
                incomplete = schedule_coverage[schedule_coverage["status"] == "incomplete"].copy()
                if not incomplete.empty:
                    st.warning(
                        f"{len(incomplete)} teams have fewer than 12 scheduled games in the loaded schedule data. "
                        "Projected win totals for those teams are not reliable until the schedule is refreshed."
                    )
                    with st.expander("Incomplete schedule audit"):
                        st.dataframe(
                            incomplete[["team", "conference", "schedule_games", "missing_games"]],
                            width="stretch",
                            hide_index=True,
                        )

            totals_display = win_totals.copy().sort_values("projected_wins", ascending=False)
            totals_display.columns = [
                "Team",
                "Conference",
                "Rating",
                "Projected Wins",
                "Projected Losses",
                "Schedule Games",
                "Projected SOS",
                "Avg Game Win %",
            ]
            st.dataframe(totals_display, width="stretch", height=520, hide_index=True)

            if not projected_games.empty:
                team_names = totals_display["Team"].tolist()
                selected_team = st.selectbox("Schedule detail", team_names, key="schedule_detail_team")
                team_games = add_game_type_column(add_week_display_columns(projected_games))
                team_games = team_games[team_games["team"] == selected_team].copy().sort_values(["display_week", "week"])
                team_games = team_games[
                    [
                        "week_label",
                        "team",
                        "opponent",
                        "game_type",
                        "site",
                        "team_rating",
                        "opponent_rating",
                        "projected_spread",
                        "favorite",
                        "favorite_spread",
                        "win_probability",
                    ]
                ].copy()
                team_games.columns = [
                    "Week",
                    "Team",
                    "Opponent",
                    "Game Type",
                    "Site",
                    "Team Rating",
                    "Opponent Rating",
                    "Projected Spread",
                    "Favorite",
                    "Favorite Spread",
                    "Win Probability",
                ]
                st.dataframe(team_games, width="stretch", hide_index=True)

    with odds_tab:
        if odds.empty:
            render_missing_state(Path(odds_path), "Odds comparison file")
        else:
            odds_board = add_game_type_column(add_week_display_columns(odds))
            numeric_columns = [
                "week",
                "display_week",
                "book_count",
                "model_home_margin",
                "model_home_spread",
                "market_home_spread",
                "market_home_margin",
                "edge_home_points",
                "absolute_edge_points",
                "actual_home_points",
                "actual_away_points",
                "actual_home_margin",
                "selected_best_spread",
                "selected_best_price",
                "break_even_probability",
                "line_shopping_value",
            ]
            for column in numeric_columns:
                if column in odds_board.columns:
                    odds_board[column] = pd.to_numeric(odds_board[column], errors="coerce")
            if "market_status" not in odds_board.columns:
                odds_board["market_status"] = "open_market"
            if "edge_review_flag" not in odds_board.columns:
                odds_board["edge_review_flag"] = "Standard"
            if "betting_status" not in odds_board.columns:
                odds_board["betting_status"] = "Standard"
            if "schedule_match_status" not in odds_board.columns:
                odds_board["schedule_match_status"] = ""
            for column in [
                "selected_best_spread",
                "selected_best_price",
                "break_even_probability",
                "line_shopping_value",
            ]:
                if column not in odds_board.columns:
                    odds_board[column] = pd.NA
            if "selected_best_book" not in odds_board.columns:
                odds_board["selected_best_book"] = ""

            live_odds = odds_board[odds_board["market_home_spread"].notna()].copy()
            no_current_odds = odds_board[odds_board["market_home_spread"].isna()].copy()
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            metric_col1.metric("Live Odds Games", f"{len(live_odds)}")
            metric_col2.metric("Completed No-Odds", f"{len(no_current_odds)}")
            metric_col3.metric("Largest Live Edge", f"{live_odds['absolute_edge_points'].max():.2f}" if not live_odds.empty else "N/A")

            st.subheader("Podcast Shortlist")
            st.caption(
                "A conservative starting list for discussion. It requires FBS games, 3-8.5 point edges, "
                "at least four books, medium-or-better team confidence, prices of -120 or better, spreads no larger "
                "than 14, small internal rating gaps, and agreement between both rating components."
            )
            podcast_shortlist = build_podcast_shortlist(odds_board, ratings)
            if podcast_shortlist.empty:
                st.info("No games currently satisfy every podcast-shortlist safeguard.")
            else:
                shortlist_details = podcast_shortlist.head(6).copy()
                shortlist_display = shortlist_details.drop(columns=["Reasoning", "Caution"]).copy()
                shortlist_display.insert(0, "Rank", range(1, len(shortlist_display) + 1))
                shortlist_display["Kickoff"] = pd.to_datetime(shortlist_display["Kickoff"], errors="coerce", utc=True).dt.strftime(
                    "%a %I:%M %p UTC"
                )
                shortlist_display["Model Fair Line"] = shortlist_display["Model Fair Line"].map(
                    lambda value: f"{float(value):+.1f}"
                )
                shortlist_display["Best Line"] = shortlist_display["Best Line"].map(lambda value: f"{float(value):+.1f}")
                shortlist_display["Price"] = shortlist_display["Price"].map(lambda value: f"{int(value):+d}")
                shortlist_display["Model Edge"] = shortlist_display["Model Edge"].map(lambda value: f"{float(value):.2f}")
                shortlist_display["Line Shopping Gain"] = shortlist_display["Line Shopping Gain"].map(
                    lambda value: f"{float(value):.2f}"
                )
                st.dataframe(shortlist_display, width="stretch", hide_index=True)
                with st.expander("Why these games made the list"):
                    for rank, (_, candidate) in enumerate(shortlist_details.iterrows(), start=1):
                        st.markdown(
                            f"**{rank}. {candidate['Model Lean']} {float(candidate['Best Line']):+.1f} "
                            f"({int(candidate['Price']):+d}, {candidate['Book']})**"
                        )
                        st.write(candidate["Reasoning"])
                        st.caption(f"Caution: {candidate['Caution']}")
                st.warning(
                    "The Candidate Score ranks data quality and signal agreement; it is not a validated cover probability. "
                    "Confirm injuries, weather, and the available line before recording a podcast pick."
                )

            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1, 1.4, 2])
            available_weeks = sorted(int(week) for week in odds_board["display_week"].dropna().unique()) if "display_week" in odds_board.columns else []
            week_options = {f"Week {week}": week for week in available_weeks}
            odds_game_type_options = ["All"] + sorted(odds_board["game_type"].dropna().astype(str).unique().tolist())
            market_status_options = sorted(odds_board["market_status"].dropna().astype(str).unique().tolist())
            review_flag_options = ["All"] + sorted(odds_board["edge_review_flag"].dropna().astype(str).unique().tolist())
            betting_status_options = ["All"] + sorted(odds_board["betting_status"].dropna().astype(str).unique().tolist())
            edge_side_options = ["All"] + sorted(
                side for side in odds_board["edge_side"].dropna().astype(str).unique().tolist() if side
            )
            with filter_col1:
                week_filter = st.selectbox("Week", ["All"] + list(week_options), index=0, key="odds_week_filter")
            with filter_col2:
                odds_game_type_filter = st.selectbox("Game Type", odds_game_type_options, index=0, key="odds_game_type_filter")
            with filter_col3:
                edge_range = st.slider(
                    "Edge range",
                    min_value=0.0,
                    max_value=50.0,
                    value=(2.5, 10.0),
                    step=0.5,
                    help="Very large edges are often data/model review candidates rather than clean value spots.",
                )
            with filter_col4:
                odds_search = st.text_input(
                    "Search odds board",
                    placeholder="Search by team, matchup, or edge side",
                    key="odds_search",
                ).strip().lower()

            odds_advanced = st.expander("Advanced filters and sorting")
            advanced_col1, advanced_col2, advanced_col3, advanced_col4, advanced_col5, advanced_col6 = odds_advanced.columns(6)
            with advanced_col1:
                selected_market_statuses = st.multiselect(
                    "Market status",
                    market_status_options,
                    default=market_status_options,
                    key="odds_market_status_filter",
                )
            with advanced_col2:
                edge_side_filter = st.selectbox("Edge side", edge_side_options, index=0, key="odds_edge_side_filter")
            with advanced_col3:
                review_flag_filter = st.selectbox("Review Flag", review_flag_options, index=0, key="odds_review_flag_filter")
            with advanced_col4:
                betting_status_filter = st.selectbox(
                    "Betting Status",
                    betting_status_options,
                    index=0,
                    key="odds_betting_status_filter",
                )
            with advanced_col5:
                min_books = st.number_input(
                    "Minimum books",
                    min_value=0,
                    max_value=25,
                    value=0,
                    step=1,
                    key="odds_min_books",
                )
            with advanced_col6:
                hide_no_line_games = st.checkbox("Hide no-line games", value=False, key="odds_hide_no_line")

            sort_col1, sort_col2, sort_col3 = odds_advanced.columns([1.4, 1, 1])
            odds_sort_options = {
                "Biggest edge": "absolute_edge_points",
                "Kickoff": "commence_time",
                "Most books": "book_count",
                "Model spread": "model_home_spread",
                "Market spread": "market_home_spread",
            }
            with sort_col1:
                odds_sort_label = st.selectbox("Sort odds by", list(odds_sort_options), index=0, key="odds_sort_by")
            with sort_col2:
                odds_sort_direction = st.selectbox("Direction", ["Descending", "Ascending"], index=0, key="odds_sort_direction")
            with sort_col3:
                max_odds_rows = st.number_input("Rows shown", min_value=10, max_value=250, value=75, step=5, key="odds_rows_shown")

            min_edge, max_edge = edge_range
            if week_filter != "All":
                selected_display_week = week_options[week_filter]
                week_odds = odds_board[odds_board["display_week"] == selected_display_week].copy()
                live_week_odds = week_odds[
                    (week_odds["absolute_edge_points"] >= min_edge)
                    & (week_odds["absolute_edge_points"] <= max_edge)
                ].copy()
                fallback_week_odds = week_odds[week_odds["market_home_spread"].isna()].copy()
                filtered_odds = pd.concat([live_week_odds, fallback_week_odds], ignore_index=True)
            else:
                filtered_odds = odds_board[
                    (odds_board["absolute_edge_points"] >= min_edge)
                    & (odds_board["absolute_edge_points"] <= max_edge)
                ].copy()
            if odds_game_type_filter != "All":
                filtered_odds = filtered_odds[filtered_odds["game_type"] == odds_game_type_filter]
            if selected_market_statuses:
                filtered_odds = filtered_odds[filtered_odds["market_status"].isin(selected_market_statuses)]
            if edge_side_filter != "All":
                filtered_odds = filtered_odds[filtered_odds["edge_side"] == edge_side_filter]
            if review_flag_filter != "All":
                filtered_odds = filtered_odds[filtered_odds["edge_review_flag"] == review_flag_filter]
            if betting_status_filter != "All":
                filtered_odds = filtered_odds[filtered_odds["betting_status"] == betting_status_filter]
            filtered_odds = filtered_odds[filtered_odds["book_count"].fillna(0) >= min_books]
            if hide_no_line_games:
                filtered_odds = filtered_odds[filtered_odds["market_home_spread"].notna()]
            if odds_search:
                filtered_odds = filtered_odds[
                    filtered_odds.apply(
                        lambda row: odds_search in str(row.get("home_team", "")).lower()
                        or odds_search in str(row.get("away_team", "")).lower()
                        or odds_search in str(row.get("edge_side", "")).lower(),
                        axis=1,
                    )
                ]

            sort_column = odds_sort_options[odds_sort_label]
            filtered_odds = filtered_odds.sort_values(
                sort_column,
                ascending=odds_sort_direction == "Ascending",
                na_position="last",
            )

            odds_summary_col1, odds_summary_col2, odds_summary_col3, odds_summary_col4 = st.columns(4)
            odds_summary_col1.metric("Filtered Games", f"{len(filtered_odds)}")
            odds_summary_col2.metric(
                "Avg Edge",
                f"{filtered_odds['absolute_edge_points'].mean():.2f}" if filtered_odds["absolute_edge_points"].notna().any() else "N/A",
            )
            odds_summary_col3.metric(
                "Median Edge",
                f"{filtered_odds['absolute_edge_points'].median():.2f}" if filtered_odds["absolute_edge_points"].notna().any() else "N/A",
            )
            odds_summary_col4.metric(
                "Avg Books",
                f"{filtered_odds['book_count'].mean():.1f}" if filtered_odds["book_count"].notna().any() else "N/A",
            )

            filtered_odds["matchup"] = filtered_odds.apply(
                lambda row: f"{row['away_team']} at {row['home_team']}",
                axis=1,
            )
            filtered_odds["model_line"] = filtered_odds.apply(
                lambda row: f"{row['home_team']} {float(row['model_home_spread']):+.1f}",
                axis=1,
            )
            filtered_odds["market_line"] = filtered_odds.apply(
                lambda row: (
                    f"{row['home_team']} {float(row['market_home_spread']):+.1f}"
                    if pd.notna(row.get("market_home_spread"))
                    else "No current line"
                ),
                axis=1,
            )
            filtered_odds["edge_display"] = filtered_odds["absolute_edge_points"].map(
                lambda value: f"{float(value):.2f}" if pd.notna(value) else "N/A"
            )
            filtered_odds["best_line"] = filtered_odds.apply(
                lambda row: (
                    f"{row.get('edge_side')} {float(row.get('selected_best_spread')):+.1f} "
                    f"({int(row.get('selected_best_price')):+d}, {row.get('selected_best_book')})"
                    if pd.notna(row.get("selected_best_spread")) and pd.notna(row.get("selected_best_price"))
                    else "Unavailable"
                ),
                axis=1,
            )
            filtered_odds["break_even_display"] = filtered_odds["break_even_probability"].map(
                lambda value: f"{float(value) * 100:.1f}%" if pd.notna(value) else "N/A"
            )
            filtered_odds["result"] = filtered_odds.apply(
                lambda row: (
                    f"{row.get('away_team')} {int(row.get('actual_away_points'))}, {row.get('home_team')} {int(row.get('actual_home_points'))}"
                    if pd.notna(row.get("actual_away_points")) and pd.notna(row.get("actual_home_points"))
                    else ""
                ),
                axis=1,
            )

            display = filtered_odds.head(max_odds_rows)[
                [
                    "week_label",
                    "commence_time",
                    "matchup",
                    "game_type",
                    "market_status",
                    "edge_side",
                    "model_favorite",
                    "betting_status",
                    "edge_review_flag",
                    "edge_display",
                    "best_line",
                    "break_even_display",
                    "line_shopping_value",
                    "model_line",
                    "market_line",
                    "result",
                    "book_count",
                    "market_total",
                ]
            ].copy()
            display.columns = [
                "Week",
                "Kickoff",
                "Matchup",
                "Game Type",
                "Market Status",
                "Model Edge Side",
                "Model Winner",
                "Betting Status",
                "Review Flag",
                "Edge Points",
                "Best Available Line",
                "Break-Even %",
                "Line Shopping Value",
                "Model Line",
                "Market Line",
                "Result",
                "Books",
                "Market Total",
            ]
            st.dataframe(display, width="stretch", hide_index=True, height=520)

            with st.expander("Raw odds comparison"):
                st.dataframe(filtered_odds, width="stretch", hide_index=True)

    with line_history_tab:
        if clv_summary.empty:
            render_missing_state(DEFAULT_CLV_SUMMARY_PATH, "CLV summary")
        else:
            ats_validated = (
                not ats_validation.empty
                and ats_validation["validated_for_deployment"].astype(str).str.lower().eq("true").any()
            )
            if not ats_validated:
                st.warning(
                    "No ATS probability model is deployed. The held-out 2025 classifier failed to beat the baseline Brier score, "
                    "so this page shows prices, movement, and CLV without pretending the edge is a validated cover probability."
                )
            history = clv_summary.copy()
            for column in [
                "snapshot_count",
                "opening_market_home_spread",
                "latest_market_home_spread",
                "home_line_movement",
                "latest_model_edge",
                "selected_best_spread",
                "selected_best_price",
                "break_even_probability",
                "line_shopping_value",
                "opening_to_latest_value",
                "closing_side_spread",
                "best_line_clv",
            ]:
                if column in history.columns:
                    history[column] = pd.to_numeric(history[column], errors="coerce")

            tracked_col1, tracked_col2, tracked_col3, tracked_col4 = st.columns(4)
            tracked_col1.metric("Tracked Games", len(history))
            tracked_col2.metric("Odds Snapshots", int(history["snapshot_count"].sum()))
            tracked_col3.metric("Multiple Snapshots", int(history["snapshot_count"].gt(1).sum()))
            tracked_col4.metric(
                "Avg Line-Shop Gain",
                f"{history['line_shopping_value'].mean():.2f}" if history["line_shopping_value"].notna().any() else "N/A",
            )
            st.caption(
                "CLV compares the line captured when a pick was available with the final pregame consensus. "
                "Positive CLV means we secured a better number than the closing market."
            )

            history_filter_col1, history_filter_col2 = st.columns([1, 2])
            history_weeks = ["All"] + sorted(history["week_label"].dropna().astype(str).unique().tolist())
            with history_filter_col1:
                history_week = st.selectbox("Week", history_weeks, key="clv_week_filter")
            with history_filter_col2:
                history_search = st.text_input(
                    "Search line history",
                    placeholder="Search by team or edge side",
                    key="clv_search",
                ).strip().lower()

            filtered_history = history.copy()
            if history_week != "All":
                filtered_history = filtered_history[filtered_history["week_label"] == history_week]
            if history_search:
                filtered_history = filtered_history[
                    filtered_history.apply(
                        lambda row: history_search in str(row.get("home_team", "")).lower()
                        or history_search in str(row.get("away_team", "")).lower()
                        or history_search in str(row.get("edge_side", "")).lower(),
                        axis=1,
                    )
                ]
            filtered_history["matchup"] = filtered_history.apply(
                lambda row: f"{row.get('away_team')} at {row.get('home_team')}",
                axis=1,
            )
            filtered_history["break_even_display"] = filtered_history["break_even_probability"].map(
                lambda value: f"{float(value) * 100:.1f}%" if pd.notna(value) else "N/A"
            )
            history_display = filtered_history[
                [
                    "week_label",
                    "matchup",
                    "snapshot_count",
                    "opening_market_home_spread",
                    "latest_market_home_spread",
                    "home_line_movement",
                    "edge_side",
                    "latest_model_edge",
                    "selected_best_spread",
                    "selected_best_price",
                    "selected_best_book",
                    "break_even_display",
                    "line_shopping_value",
                    "opening_to_latest_value",
                    "best_line_clv",
                    "ats_result",
                    "betting_status",
                ]
            ].copy()
            history_display.columns = [
                "Week",
                "Matchup",
                "Snapshots",
                "Opening Home Line",
                "Latest Home Line",
                "Home Line Move",
                "Model Side",
                "Latest Edge",
                "Best Spread",
                "Best Price",
                "Best Book",
                "Break-Even %",
                "Line-Shop Gain",
                "Opening Value",
                "Closing-Line Value",
                "ATS Result",
                "Betting Status",
            ]
            st.dataframe(history_display, width="stretch", hide_index=True, height=520)

            with st.expander("Raw odds snapshot history"):
                st.dataframe(odds_history, width="stretch", hide_index=True)

    with team_betting_tab:
        if completed_review.empty:
            render_missing_state(Path(completed_review_path), "Completed games review file")
        else:
            team_summary, team_game_log = build_team_betting_summary(completed_review)
            if team_summary.empty or team_game_log.empty:
                st.warning("No completed games with market lines are available for team betting analysis.")
            else:
                st.caption(
                    "Team-level betting view. ATS cover rate is based on the closing/average market spread in the review file. "
                    "Edge hit rate only counts games where the model's spread edge selected that team."
                )

                betting_filter_col1, betting_filter_col2, betting_filter_col3, betting_filter_col4 = st.columns([1, 1, 1.3, 2])
                with betting_filter_col1:
                    min_team_games = st.number_input(
                        "Minimum games",
                        min_value=1,
                        max_value=20,
                        value=1,
                        step=1,
                        key="team_betting_min_games",
                    )
                with betting_filter_col2:
                    min_edge_picks = st.number_input(
                        "Minimum edge picks",
                        min_value=0,
                        max_value=20,
                        value=0,
                        step=1,
                        key="team_betting_min_edge_picks",
                    )
                with betting_filter_col3:
                    game_type_filter = st.selectbox(
                        "Game Type",
                        ["All"] + sorted(team_game_log["game_type"].dropna().astype(str).unique().tolist()),
                        index=0,
                        key="team_betting_game_type",
                    )
                with betting_filter_col4:
                    team_betting_search = st.text_input(
                        "Search teams",
                        placeholder="Start typing a team",
                        key="team_betting_search",
                    ).strip().lower()

                filtered_team_games = team_game_log.copy()
                if game_type_filter != "All":
                    filtered_team_games = filtered_team_games[filtered_team_games["game_type"] == game_type_filter]

                if filtered_team_games.empty:
                    st.info("No team-game rows match those filters.")
                else:
                    team_summary = summarize_team_betting(filtered_team_games)
                    filtered_team_summary = team_summary[
                        (team_summary["games"] >= min_team_games)
                        & (team_summary["model_edge_picks"] >= min_edge_picks)
                    ].copy()
                    if team_betting_search:
                        filtered_team_summary = filtered_team_summary[
                            filtered_team_summary["team"].str.contains(team_betting_search, case=False, na=False)
                        ]

                    sort_options = {
                        "Best ATS cover rate": "ats_cover_rate",
                        "Worst ATS cover rate": "ats_cover_rate",
                        "Best edge-pick hit rate": "edge_pick_hit_rate",
                        "Worst edge-pick hit rate": "edge_pick_hit_rate",
                        "Most edge picks": "model_edge_picks",
                        "Best avg ATS margin": "avg_ats_margin",
                        "Worst avg ATS margin": "avg_ats_margin",
                        "Largest model error": "avg_model_error",
                    }
                    sort_col1, sort_col2 = st.columns([1.4, 1])
                    with sort_col1:
                        team_sort_label = st.selectbox("Sort teams by", list(sort_options), index=0, key="team_betting_sort")
                    with sort_col2:
                        max_team_rows = st.number_input(
                            "Rows shown",
                            min_value=10,
                            max_value=250,
                            value=75,
                            step=5,
                            key="team_betting_rows",
                        )

                    ascending = team_sort_label.startswith("Worst")
                    filtered_team_summary = filtered_team_summary.sort_values(
                        sort_options[team_sort_label],
                        ascending=ascending,
                        na_position="last",
                    )

                    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                    metric_col1.metric("Teams Shown", f"{len(filtered_team_summary)}")
                    metric_col2.metric(
                        "Avg ATS Cover",
                        f"{filtered_team_summary['ats_cover_rate'].mean() * 100:.1f}%"
                        if filtered_team_summary["ats_cover_rate"].notna().any()
                        else "N/A",
                    )
                    metric_col3.metric(
                        "Avg Edge Hit",
                        f"{filtered_team_summary['edge_pick_hit_rate'].mean() * 100:.1f}%"
                        if filtered_team_summary["edge_pick_hit_rate"].notna().any()
                        else "N/A",
                    )
                    metric_col4.metric(
                        "Avg Model Error",
                        f"{filtered_team_summary['avg_model_error'].mean():.2f}"
                        if filtered_team_summary["avg_model_error"].notna().any()
                        else "N/A",
                    )

                    display = filtered_team_summary.head(max_team_rows)[
                        [
                            "team",
                            "games",
                            "ats_covers",
                            "ats_decisions",
                            "ats_cover_rate",
                            "avg_ats_margin",
                            "model_edge_picks",
                            "edge_pick_hits",
                            "edge_pick_hit_rate",
                            "avg_edge_when_picked",
                            "model_winner_accuracy",
                            "avg_model_error",
                            "avg_market_error",
                        ]
                    ].copy()
                    for column in ["ats_cover_rate", "edge_pick_hit_rate", "model_winner_accuracy"]:
                        display[column] = display[column].map(lambda value: f"{value * 100:.1f}%" if pd.notna(value) else "N/A")
                    for column in ["avg_ats_margin", "avg_edge_when_picked", "avg_model_error", "avg_market_error"]:
                        display[column] = display[column].map(lambda value: f"{value:.2f}" if pd.notna(value) else "N/A")
                    display.columns = [
                        "Team",
                        "Games",
                        "ATS Covers",
                        "ATS Decisions",
                        "ATS Cover %",
                        "Avg ATS Margin",
                        "Model Edge Picks",
                        "Edge Hits",
                        "Edge Hit %",
                        "Avg Edge Pick",
                        "Winner Pick %",
                        "Model Error",
                        "Market Error",
                    ]
                    st.dataframe(display, width="stretch", hide_index=True, height=520)

                    st.subheader("Team Game Log")
                    selected_team = st.selectbox(
                        "Team detail",
                        filtered_team_summary["team"].tolist() if not filtered_team_summary.empty else sorted(filtered_team_games["team"].unique().tolist()),
                        key="team_betting_detail_team",
                    )
                    detail = filtered_team_games[filtered_team_games["team"] == selected_team].sort_values(["display_week", "opponent"]).copy()
                    detail["score"] = detail.apply(
                        lambda row: f"{int(row['points_for'])}-{int(row['points_against'])}",
                        axis=1,
                    )
                    detail_display = detail[
                        [
                            "week_label",
                            "opponent",
                            "game_type",
                            "site",
                            "score",
                            "market_spread",
                            "ats_margin",
                            "ats_result",
                            "model_margin",
                            "model_edge",
                            "model_edge_pick",
                            "model_edge_hit",
                        ]
                    ].copy()
                    detail_display.columns = [
                        "Week",
                        "Opponent",
                        "Game Type",
                        "Site",
                        "Score",
                        "Market Spread",
                        "ATS Margin",
                        "ATS Result",
                        "Model Margin",
                        "Model Edge",
                        "Model Picked Team",
                        "Edge Hit",
                    ]
                    st.dataframe(detail_display, width="stretch", hide_index=True)

    with analytics_tab:
        analytics_frames = [
            edge_bucket_summary,
            split_summary,
            team_bias,
            conference_summary,
            big_misses,
            market_disagreements,
            probability_calibration,
        ]
        if all(frame.empty for frame in analytics_frames):
            render_missing_state(Path(edge_bucket_default), "Betting analytics files")
        else:
            st.caption(
                "Statistical tracking layer for model health. These tables are regenerated during each refresh and saved in "
                "`output/analytics` plus the master workbook."
            )

            analytics_section = st.selectbox(
                "Analytics view",
                [
                    "Edge Buckets",
                    "Splits",
                    "Probability Calibration",
                    "Team Bias",
                    "Conference Summary",
                    "Big Misses",
                    "Market Disagreements",
                ],
                index=0,
                key="analytics_view",
            )

            if analytics_section == "Edge Buckets":
                if edge_bucket_summary.empty:
                    render_missing_state(Path(edge_bucket_default), "Edge bucket summary")
                else:
                    display = edge_bucket_summary.copy()
                    st.write("How model edge size has performed against the market and actual results.")
                    st.dataframe(display, width="stretch", hide_index=True)

            elif analytics_section == "Splits":
                if split_summary.empty:
                    render_missing_state(Path(split_summary_default), "Split summary")
                else:
                    split_options = ["All"] + sorted(split_summary["split"].dropna().astype(str).unique().tolist())
                    selected_split = st.selectbox("Split", split_options, index=0, key="analytics_split_filter")
                    display = split_summary.copy()
                    if selected_split != "All":
                        display = display[display["split"] == selected_split]
                    st.write("Performance split by game type, pick role, pick site, and week.")
                    st.dataframe(display, width="stretch", hide_index=True)

            elif analytics_section == "Probability Calibration":
                if probability_calibration.empty:
                    render_missing_state(Path(probability_calibration_default), "Probability calibration")
                else:
                    st.write("Checks whether model win probabilities are calibrated to actual win rates.")
                    chart = probability_calibration.copy()
                    for column in ["average_model_probability", "actual_win_rate"]:
                        chart[column] = pd.to_numeric(chart[column], errors="coerce")
                    st.line_chart(
                        chart.set_index("win_probability_bucket")[["average_model_probability", "actual_win_rate"]],
                        width="stretch",
                    )
                    st.dataframe(probability_calibration, width="stretch", hide_index=True)

            elif analytics_section == "Team Bias":
                if team_bias.empty:
                    render_missing_state(Path(team_bias_default), "Team bias")
                else:
                    bias = team_bias.copy()
                    for column in [
                        "games",
                        "ats_cover_rate",
                        "average_ats_margin",
                        "average_model_bias_margin",
                        "model_edge_picks",
                        "edge_pick_hit_rate",
                        "model_margin_mae",
                        "market_margin_mae",
                    ]:
                        bias[column] = pd.to_numeric(bias[column], errors="coerce")
                    bias_col1, bias_col2, bias_col3 = st.columns([1, 1, 2])
                    with bias_col1:
                        min_bias_games = st.number_input("Minimum games", min_value=1, max_value=20, value=1, step=1, key="analytics_bias_min_games")
                    with bias_col2:
                        bias_sort = st.selectbox(
                            "Sort by",
                            ["Largest absolute bias", "Most overrated", "Most underrated", "Worst model error", "Best ATS cover"],
                            index=0,
                            key="analytics_bias_sort",
                        )
                    with bias_col3:
                        bias_search = st.text_input("Search team/conference", key="analytics_bias_search").strip().lower()
                    bias = bias[bias["games"] >= min_bias_games]
                    if bias_search:
                        bias = bias[
                            bias.apply(
                                lambda row: bias_search in str(row.get("team", "")).lower()
                                or bias_search in str(row.get("conference", "")).lower(),
                                axis=1,
                            )
                        ]
                    if bias_sort == "Largest absolute bias":
                        bias = bias.assign(abs_bias=bias["average_model_bias_margin"].abs()).sort_values("abs_bias", ascending=False)
                    elif bias_sort == "Most overrated":
                        bias = bias.sort_values("average_model_bias_margin", ascending=False)
                    elif bias_sort == "Most underrated":
                        bias = bias.sort_values("average_model_bias_margin", ascending=True)
                    elif bias_sort == "Worst model error":
                        bias = bias.sort_values("model_margin_mae", ascending=False)
                    else:
                        bias = bias.sort_values("ats_cover_rate", ascending=False)
                    st.write("Positive model bias means the model has overrated that team versus actual margins.")
                    st.dataframe(bias.drop(columns=["abs_bias"], errors="ignore"), width="stretch", hide_index=True, height=520)

            elif analytics_section == "Conference Summary":
                if conference_summary.empty:
                    render_missing_state(Path(conference_summary_default), "Conference summary")
                else:
                    st.write("Conference-level rollup of team bias and error metrics.")
                    st.dataframe(conference_summary, width="stretch", hide_index=True)

            elif analytics_section == "Big Misses":
                if big_misses.empty:
                    render_missing_state(Path(big_misses_default), "Big misses")
                else:
                    miss = big_misses.copy()
                    miss["absolute_model_error"] = pd.to_numeric(miss["absolute_model_error"], errors="coerce")
                    min_miss = st.slider("Minimum model error", min_value=20.0, max_value=60.0, value=20.0, step=1.0, key="analytics_min_miss")
                    miss = miss[miss["absolute_model_error"] >= min_miss].sort_values("absolute_model_error", ascending=False)
                    st.write("Games where the model missed the final margin badly enough to deserve review.")
                    st.dataframe(miss, width="stretch", hide_index=True, height=520)

            elif analytics_section == "Market Disagreements":
                if market_disagreements.empty:
                    st.info("No games yet where the model and market disagreed on the winner.")
                else:
                    st.write("Games where the model and market picked different outright winners.")
                    st.dataframe(market_disagreements, width="stretch", hide_index=True)

    with review_tab:
        if weekly_review.empty or completed_review.empty:
            render_missing_state(Path(completed_review_path), "Completed games review file")
        else:
            weekly_results = add_week_display_columns(weekly_review)
            completed_games = add_game_type_column(add_week_display_columns(completed_review))
            if "betting_status" not in completed_games.columns:
                completed_games["betting_status"] = "Standard"
            if "rating_source" not in completed_games.columns:
                completed_games["rating_source"] = "Legacy"
            for column in [
                "display_week",
                "games",
                "games_with_market_line",
                "model_margin_mae",
                "market_margin_mae",
                "model_winner_accuracy",
                "market_winner_accuracy",
                "edge_right_side_rate",
                "actual_home_margin",
                "model_home_margin",
                "market_home_margin",
                "absolute_model_error",
                "absolute_market_error",
                "model_edge_home_points",
            ]:
                if column in weekly_results.columns:
                    weekly_results[column] = pd.to_numeric(weekly_results[column], errors="coerce")
                if column in completed_games.columns:
                    completed_games[column] = pd.to_numeric(completed_games[column], errors="coerce")

            review_col1, review_col2, review_col3, review_col4 = st.columns(4)
            total_completed = int(weekly_results["games"].sum())
            market_games = int(weekly_results["games_with_market_line"].sum())
            weighted_model_mae = (
                (weekly_results["model_margin_mae"] * weekly_results["games"]).sum() / total_completed
                if total_completed
                else 0.0
            )
            weighted_market_mae = (
                (weekly_results["market_margin_mae"] * weekly_results["games_with_market_line"]).sum() / market_games
                if market_games
                else 0.0
            )
            review_col1.metric("Completed Games", f"{total_completed}")
            review_col2.metric("With Market Line", f"{market_games}")
            review_col3.metric("Model Margin MAE", f"{weighted_model_mae:.2f}")
            review_col4.metric("Market Margin MAE", f"{weighted_market_mae:.2f}" if market_games else "N/A")

            st.subheader("Weekly Sanity Check")
            weekly_display = weekly_results[
                [
                    "week_label",
                    "games",
                    "games_with_market_line",
                    "model_margin_mae",
                    "market_margin_mae",
                    "model_winner_accuracy",
                    "market_winner_accuracy",
                    "edge_right_side_rate",
                ]
            ].copy()
            weekly_display.columns = [
                "Week",
                "Games",
                "Market Games",
                "Model Margin MAE",
                "Market Margin MAE",
                "Model Winner %",
                "Market Winner %",
                "Edge Right-Side %",
            ]
            st.dataframe(weekly_display, width="stretch", hide_index=True)

            st.subheader("Game-Level Review")
            completed_games["matchup"] = completed_games.apply(
                lambda row: f"{row['away_team']} at {row['home_team']}",
                axis=1,
            )
            completed_games["score"] = completed_games.apply(
                lambda row: f"{row['away_team']} {int(row['away_points'])}, {row['home_team']} {int(row['home_points'])}",
                axis=1,
            )
            completed_games["model_line"] = completed_games.apply(
                lambda row: f"{row['home_team']} {float(row['model_home_spread']):+.1f}",
                axis=1,
            )
            completed_games["market_line"] = completed_games.apply(
                lambda row: (
                    f"{row['home_team']} {float(row['market_home_spread']):+.1f}"
                    if pd.notna(row.get("market_home_spread")) and row.get("market_home_spread") != ""
                    else "No market line"
                ),
                axis=1,
            )
            completed_games["model_winner"] = completed_games.apply(
                lambda row: row["home_team"] if row["model_home_margin"] >= 0 else row["away_team"],
                axis=1,
            )

            available_review_weeks = sorted(int(week) for week in completed_games["display_week"].dropna().unique())
            review_week_options = {f"Week {week}": week for week in available_review_weeks}
            review_game_type_options = ["All"] + sorted(completed_games["game_type"].dropna().astype(str).unique().tolist())
            winner_result_options = ["All"] + sorted(completed_games["winner_model_result"].dropna().astype(str).unique().tolist())
            rating_source_options = ["All"] + sorted(completed_games["rating_source"].dropna().astype(str).unique().tolist())
            edge_result_options = ["All"] + sorted(
                result for result in completed_games["edge_result"].dropna().astype(str).unique().tolist() if result
            )
            review_betting_status_options = ["All"] + sorted(
                completed_games["betting_status"].dropna().astype(str).unique().tolist()
            )
            review_filter_col1, review_filter_col2, review_filter_col3, review_filter_col4, review_filter_col5 = st.columns([1, 1, 1, 1.4, 2])
            with review_filter_col1:
                review_week_filter = st.selectbox("Week", ["All"] + list(review_week_options), index=0, key="results_review_week")
            with review_filter_col2:
                review_game_type_filter = st.selectbox("Game Type", review_game_type_options, index=0, key="results_review_game_type")
            with review_filter_col3:
                winner_result_filter = st.selectbox("Winner Pick", winner_result_options, index=0, key="results_review_winner_result")
            with review_filter_col4:
                rating_source_filter = st.selectbox(
                    "Rating Source",
                    rating_source_options,
                    index=0,
                    key="results_review_rating_source",
                )
            with review_filter_col5:
                review_search = st.text_input(
                    "Search completed games",
                    placeholder="Search by team, matchup, or result",
                    key="results_review_search",
                ).strip().lower()

            review_advanced = st.expander("Advanced filters and sorting")
            review_advanced_col1, review_advanced_col2, review_advanced_col3, review_advanced_col4, review_advanced_col5 = review_advanced.columns(5)
            with review_advanced_col1:
                edge_result_filter = st.selectbox("Edge Result", edge_result_options, index=0, key="results_review_edge_result")
            with review_advanced_col2:
                review_betting_status_filter = st.selectbox(
                    "Betting Status",
                    review_betting_status_options,
                    index=0,
                    key="results_review_betting_status",
                )
            with review_advanced_col3:
                min_model_error = st.slider(
                    "Min model error",
                    min_value=0.0,
                    max_value=60.0,
                    value=0.0,
                    step=1.0,
                    key="results_review_min_model_error",
                )
            with review_advanced_col4:
                error_view = st.selectbox(
                    "Error view",
                    ["All games", "Model worse than market", "Model better than market", "No market line"],
                    index=0,
                    key="results_review_error_view",
                )
            with review_advanced_col5:
                min_edge_size = st.slider(
                    "Min edge size",
                    min_value=0.0,
                    max_value=50.0,
                    value=0.0,
                    step=0.5,
                    help="Uses absolute model edge versus market when a market line exists.",
                    key="results_review_min_edge_size",
                )

            review_sort_col1, review_sort_col2, review_sort_col3 = review_advanced.columns([1.4, 1, 1])
            review_sort_options = {
                "Biggest model error": "absolute_model_error",
                "Biggest market error": "absolute_market_error",
                "Largest model edge": "absolute_model_edge",
                "Kickoff": "start_date",
                "Actual margin": "actual_home_margin",
            }
            with review_sort_col1:
                review_sort_label = st.selectbox("Sort review by", list(review_sort_options), index=0, key="results_review_sort_by")
            with review_sort_col2:
                review_sort_direction = st.selectbox("Direction", ["Descending", "Ascending"], index=0, key="results_review_sort_direction")
            with review_sort_col3:
                max_review_rows = st.number_input("Rows shown", min_value=10, max_value=250, value=75, step=5, key="results_review_rows_shown")

            filtered_review = completed_games.copy()
            filtered_review["absolute_model_edge"] = filtered_review["model_edge_home_points"].abs()
            if review_week_filter != "All":
                filtered_review = filtered_review[filtered_review["display_week"] == review_week_options[review_week_filter]]
            if review_game_type_filter != "All":
                filtered_review = filtered_review[filtered_review["game_type"] == review_game_type_filter]
            if winner_result_filter != "All":
                filtered_review = filtered_review[filtered_review["winner_model_result"] == winner_result_filter]
            if rating_source_filter != "All":
                filtered_review = filtered_review[filtered_review["rating_source"] == rating_source_filter]
            if edge_result_filter != "All":
                filtered_review = filtered_review[filtered_review["edge_result"] == edge_result_filter]
            if review_betting_status_filter != "All":
                filtered_review = filtered_review[filtered_review["betting_status"] == review_betting_status_filter]
            filtered_review = filtered_review[filtered_review["absolute_model_error"].fillna(0) >= min_model_error]
            filtered_review = filtered_review[filtered_review["absolute_model_edge"].fillna(0) >= min_edge_size]
            if error_view == "Model worse than market":
                filtered_review = filtered_review[
                    filtered_review["absolute_market_error"].notna()
                    & (filtered_review["absolute_model_error"] > filtered_review["absolute_market_error"])
                ]
            elif error_view == "Model better than market":
                filtered_review = filtered_review[
                    filtered_review["absolute_market_error"].notna()
                    & (filtered_review["absolute_model_error"] < filtered_review["absolute_market_error"])
                ]
            elif error_view == "No market line":
                filtered_review = filtered_review[filtered_review["absolute_market_error"].isna()]
            if review_search:
                filtered_review = filtered_review[
                    filtered_review.apply(
                        lambda row: review_search in str(row.get("matchup", "")).lower()
                        or review_search in str(row.get("winner_model_result", "")).lower()
                        or review_search in str(row.get("edge_result", "")).lower(),
                        axis=1,
                    )
                ]

            review_sort_column = review_sort_options[review_sort_label]
            filtered_review = filtered_review.sort_values(
                review_sort_column,
                ascending=review_sort_direction == "Ascending",
                na_position="last",
            )

            review_summary_col1, review_summary_col2, review_summary_col3, review_summary_col4 = st.columns(4)
            review_summary_col1.metric("Filtered Games", f"{len(filtered_review)}")
            review_summary_col2.metric(
                "Model Error",
                f"{filtered_review['absolute_model_error'].mean():.2f}" if filtered_review["absolute_model_error"].notna().any() else "N/A",
            )
            review_summary_col3.metric(
                "Market Error",
                f"{filtered_review['absolute_market_error'].mean():.2f}" if filtered_review["absolute_market_error"].notna().any() else "N/A",
            )
            review_summary_col4.metric(
                "Winner Hit Rate",
                f"{(filtered_review['winner_model_result'].eq('correct').mean() * 100):.1f}%" if not filtered_review.empty else "N/A",
            )

            review_game_display = filtered_review.head(max_review_rows)[
                [
                    "week_label",
                    "matchup",
                    "game_type",
                    "rating_source",
                    "score",
                    "model_line",
                    "market_line",
                    "actual_home_margin",
                    "absolute_model_error",
                    "absolute_market_error",
                    "absolute_model_edge",
                    "model_winner",
                    "betting_status",
                    "winner_model_result",
                    "edge_result",
                ]
            ].copy()
            review_game_display.columns = [
                "Week",
                "Matchup",
                "Game Type",
                "Rating Source",
                "Final Score",
                "Model Line",
                "Market Line",
                "Actual Home Margin",
                "Model Error",
                "Market Error",
                "Model Edge",
                "Model Winner",
                "Betting Status",
                "Winner Pick",
                "Edge Result",
            ]
            st.dataframe(review_game_display, width="stretch", hide_index=True, height=520)

    with backtest_tab:
        st.subheader("Margin Challenger Gate")
        if margin_challenger_validation.empty:
            render_missing_state(DEFAULT_MARGIN_CHALLENGER_PATH, "Margin challenger validation")
        else:
            held_out = margin_challenger_validation[
                margin_challenger_validation["stage"].eq("2025_held_out_test")
            ]
            held_out = held_out.iloc[0] if not held_out.empty else margin_challenger_validation.iloc[-1]
            challenger_col1, challenger_col2, challenger_col3 = st.columns(3)
            challenger_col1.metric("Market Margin MAE", f"{float(held_out['market_mae']):.3f}")
            challenger_col2.metric("Challenger Margin MAE", f"{float(held_out['challenger_mae']):.3f}")
            challenger_col3.metric("Improvement", f"{float(held_out['mae_improvement']):+.3f}")
            st.info(
                "The matchup residual challenger remains research-only because it did not improve held-out 2025 "
                "margin accuracy. Failed challengers are retained here instead of silently changing production."
            )

        st.subheader("Historical Weekly Backtest")
        if backtest.empty:
            render_missing_state(Path(backtest_path), "Backtest file")
        else:
            total_games = int(backtest["games"].sum())
            weighted_mae = (backtest["model_vs_market_mae"] * backtest["games"]).sum() / total_games
            weighted_corr = (backtest["model_vs_market_corr"] * backtest["games"]).sum() / total_games
            col1, col2, col3 = st.columns(3)
            col1.metric("Tracked Games", f"{total_games}")
            col2.metric("Weighted MAE", f"{weighted_mae:.3f}")
            col3.metric("Weighted Corr", f"{weighted_corr:.3f}")

            chart_df = backtest.set_index("week")[
                ["model_vs_market_mae", "model_vs_actual_mae", "actual_vs_market_mae"]
            ]
            st.line_chart(chart_df, width="stretch")
            st.dataframe(backtest, width="stretch", hide_index=True)

if __name__ == "__main__":
    main()

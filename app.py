from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_BACKTEST_PATH = Path("output/backtests/weekly_backtest_2025_regular.csv")
DEFAULT_EXCEL_PATH = Path("output/power_ratings_final.xlsx")
DEFAULT_WIN_TOTALS_PATH = Path("output/projections/projected_win_totals_2026.csv")
DEFAULT_PROJECTED_GAMES_PATH = Path("output/projections/projected_games_2026.csv")
DEFAULT_SCHEDULE_COVERAGE_PATH = Path("output/projections/schedule_coverage_2026.csv")
DEFAULT_ODDS_COMPARISON_PATH = Path("output/odds/ncaaf_game_odds_comparison.csv")
DEFAULT_WEEKLY_RESULTS_REVIEW_PATH = Path("output/reviews/weekly_results_review_2026.csv")
DEFAULT_COMPLETED_GAMES_REVIEW_PATH = Path("output/reviews/completed_games_review_2026.csv")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_uploaded_csv(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    return pd.read_csv(uploaded_file)


def discover_csv_options(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(str(path) for path in root.rglob("*.csv"))


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


def render_missing_state(path: Path, label: str) -> None:
    st.warning(f"{label} was not found at `{path}`.")


def main() -> None:
    st.set_page_config(
        page_title="College Football Power Ratings",
        page_icon="🏈",
        layout="wide",
    )

    st.title("College Football Power Ratings")
    st.caption("Market-calibrated college football power numbers with matchup and backtest views.")

    discovered_csvs = discover_csv_options(Path("output"))
    ratings_default = str(DEFAULT_RATINGS_PATH)
    backtest_default = str(DEFAULT_BACKTEST_PATH)
    win_totals_default = str(DEFAULT_WIN_TOTALS_PATH)
    projected_games_default = str(DEFAULT_PROJECTED_GAMES_PATH)
    schedule_coverage_default = str(DEFAULT_SCHEDULE_COVERAGE_PATH)
    odds_default = str(DEFAULT_ODDS_COMPARISON_PATH)
    weekly_review_default = str(DEFAULT_WEEKLY_RESULTS_REVIEW_PATH)
    completed_review_default = str(DEFAULT_COMPLETED_GAMES_REVIEW_PATH)

    st.sidebar.subheader("Data Sources")
    ratings_path = st.sidebar.selectbox(
        "Ratings CSV",
        options=discovered_csvs if discovered_csvs else [ratings_default],
        index=discovered_csvs.index(ratings_default) if ratings_default in discovered_csvs else 0,
    )
    backtest_options = [path for path in discovered_csvs if "backtest" in path.lower()]
    backtest_path = st.sidebar.selectbox(
        "Backtest CSV",
        options=backtest_options if backtest_options else [backtest_default],
        index=backtest_options.index(backtest_default) if backtest_default in backtest_options else 0,
    )
    projection_options = [path for path in discovered_csvs if "projected_win_totals" in path.lower()]
    projected_games_options = [path for path in discovered_csvs if "projected_games" in path.lower()]
    win_totals_path = st.sidebar.selectbox(
        "Projected Win Totals CSV",
        options=projection_options if projection_options else [win_totals_default],
        index=projection_options.index(win_totals_default) if win_totals_default in projection_options else 0,
    )
    projected_games_path = st.sidebar.selectbox(
        "Projected Games CSV",
        options=projected_games_options if projected_games_options else [projected_games_default],
        index=projected_games_options.index(projected_games_default) if projected_games_default in projected_games_options else 0,
    )
    schedule_coverage_options = [path for path in discovered_csvs if "schedule_coverage" in path.lower()]
    schedule_coverage_path = st.sidebar.selectbox(
        "Schedule Coverage CSV",
        options=schedule_coverage_options if schedule_coverage_options else [schedule_coverage_default],
        index=schedule_coverage_options.index(schedule_coverage_default) if schedule_coverage_default in schedule_coverage_options else 0,
    )
    odds_options = [path for path in discovered_csvs if "odds" in path.lower()]
    odds_path = st.sidebar.selectbox(
        "Odds Comparison CSV",
        options=odds_options if odds_options else [odds_default],
        index=odds_options.index(odds_default) if odds_default in odds_options else 0,
    )
    review_options = [path for path in discovered_csvs if "results_review" in path.lower() or "completed_games_review" in path.lower()]
    weekly_review_path = st.sidebar.selectbox(
        "Weekly Results Review CSV",
        options=review_options if review_options else [weekly_review_default],
        index=review_options.index(weekly_review_default) if weekly_review_default in review_options else 0,
    )
    completed_review_path = st.sidebar.selectbox(
        "Completed Games Review CSV",
        options=review_options if review_options else [completed_review_default],
        index=review_options.index(completed_review_default) if completed_review_default in review_options else 0,
    )
    excel_path = st.sidebar.text_input("Excel Workbook", str(DEFAULT_EXCEL_PATH))

    st.sidebar.subheader("Hosted Fallback")
    uploaded_ratings = st.sidebar.file_uploader("Upload ratings CSV", type="csv")
    uploaded_backtest = st.sidebar.file_uploader("Upload backtest CSV", type="csv")
    uploaded_win_totals = st.sidebar.file_uploader("Upload projected win totals CSV", type="csv")
    uploaded_projected_games = st.sidebar.file_uploader("Upload projected games CSV", type="csv")
    uploaded_schedule_coverage = st.sidebar.file_uploader("Upload schedule coverage CSV", type="csv")
    uploaded_odds = st.sidebar.file_uploader("Upload odds comparison CSV", type="csv")
    uploaded_weekly_review = st.sidebar.file_uploader("Upload weekly results review CSV", type="csv")
    uploaded_completed_review = st.sidebar.file_uploader("Upload completed games review CSV", type="csv")
    uploaded_excel = st.sidebar.file_uploader("Upload Excel workbook", type=["xlsx"])

    ratings = load_uploaded_csv(uploaded_ratings) if uploaded_ratings else load_csv(Path(ratings_path))
    backtest = load_uploaded_csv(uploaded_backtest) if uploaded_backtest else load_csv(Path(backtest_path))
    win_totals = load_uploaded_csv(uploaded_win_totals) if uploaded_win_totals else load_csv(Path(win_totals_path))
    projected_games = load_uploaded_csv(uploaded_projected_games) if uploaded_projected_games else load_csv(Path(projected_games_path))
    schedule_coverage = load_uploaded_csv(uploaded_schedule_coverage) if uploaded_schedule_coverage else load_csv(Path(schedule_coverage_path))
    odds = load_uploaded_csv(uploaded_odds) if uploaded_odds else load_csv(Path(odds_path))
    weekly_review = load_uploaded_csv(uploaded_weekly_review) if uploaded_weekly_review else load_csv(Path(weekly_review_path))
    completed_review = load_uploaded_csv(uploaded_completed_review) if uploaded_completed_review else load_csv(Path(completed_review_path))

    if ratings.empty:
        render_missing_state(Path(ratings_path), "Ratings file")
        st.info("On Streamlit Cloud, either commit the latest output files to the repo or upload them from the sidebar.")
        st.stop()

    ratings = ratings.sort_values("rating", ascending=False).reset_index(drop=True)
    ratings.index = ratings.index + 1

    top_row = ratings.iloc[0]
    st.markdown(
        f"""
        <div style="padding: 1rem 1.2rem; border-radius: 18px; background: linear-gradient(135deg, #14324a, #b6461d); color: white; margin-bottom: 1rem;">
          <div style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.12em; opacity: 0.85;">Current No. 1</div>
          <div style="font-size: 2rem; font-weight: 700;">{top_row['team']}</div>
          <div style="font-size: 1rem; opacity: 0.92;">Rating {top_row['rating']:.2f} | Record {top_row['record']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rankings_tab, matchup_tab, weekly_tab, win_totals_tab, odds_tab, review_tab, backtest_tab, files_tab = st.tabs(
        ["Rankings", "Matchup", "Weekly Matchups", "Projected Wins", "Odds / Edges", "Results Review", "Backtest", "Files"]
    )

    with rankings_tab:
        conferences = ["All conferences"] + sorted(ratings["conference"].dropna().astype(str).unique().tolist())
        selected_conference = st.selectbox("Conference", conferences, index=0)
        search_term = st.text_input("Team search", placeholder="Start typing a team name")

        filtered = ratings.copy()
        if selected_conference != "All conferences":
            filtered = filtered[filtered["conference"] == selected_conference]
        if search_term:
            filtered = filtered[filtered["team"].str.contains(search_term, case=False, na=False)]

        display = filtered[
            ["team", "conference", "record", "rating", "efficiency_score", "market_score", "schedule_score"]
        ].copy()
        display.columns = ["Team", "Conference", "Record", "Rating", "Efficiency", "Market", "Schedule"]
        st.dataframe(display, use_container_width=True, height=620)

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
                    "Record": team_a["record"],
                    "Efficiency": float(team_a["efficiency_score"]),
                    "Market": float(team_a["market_score"]),
                    "Schedule": float(team_a["schedule_score"]),
                },
                {
                    "Team": team_b_name,
                    "Rating": float(team_b["rating"]),
                    "Record": team_b["record"],
                    "Efficiency": float(team_b["efficiency_score"]),
                    "Market": float(team_b["market_score"]),
                    "Schedule": float(team_b["schedule_score"]),
                },
            ]
        )
        st.dataframe(comparison, use_container_width=True, hide_index=True)

    with weekly_tab:
        if projected_games.empty:
            render_missing_state(Path(projected_games_path), "Projected games file")
        else:
            weekly_board = add_week_display_columns(projected_games)
            weekly_board["week"] = weekly_board["week"].astype(int)
            available_weeks = sorted(int(week) for week in weekly_board["display_week"].dropna().unique())
            week_options = {f"Week {week}": week for week in available_weeks}
            filter_col1, filter_col2 = st.columns([1, 2])
            with filter_col1:
                selected_week_label = st.selectbox("Week", list(week_options), index=0, key="weekly_matchup_week")
                selected_week = week_options[selected_week_label]
            with filter_col2:
                matchup_search = st.text_input(
                    "Search weekly matchups",
                    placeholder="Search by team, opponent, or favorite",
                    key="weekly_matchup_search",
                ).strip().lower()
            board = weekly_board[weekly_board["display_week"] == selected_week].copy()
            board = board[board["site"].isin(["home", "neutral"])].copy()

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
                ["week_label", "matchup", "site", "line", "win_probability", "team_rating", "opponent_rating"]
            ].copy()
            display.columns = [
                "Week",
                "Matchup",
                "Site",
                "Projected Line",
                "Home/Listed Team Win %",
                "Listed Team Rating",
                "Opponent Rating",
            ]
            display["Home/Listed Team Win %"] = display["Home/Listed Team Win %"].map(lambda value: f"{float(value) * 100:.1f}%")
            st.dataframe(display, use_container_width=True, hide_index=True, height=520)

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
                            use_container_width=True,
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
            st.dataframe(totals_display, use_container_width=True, height=520, hide_index=True)

            if not projected_games.empty:
                team_names = totals_display["Team"].tolist()
                selected_team = st.selectbox("Schedule detail", team_names, key="schedule_detail_team")
                team_games = add_week_display_columns(projected_games)
                team_games = team_games[team_games["team"] == selected_team].copy().sort_values(["display_week", "week"])
                team_games = team_games[
                    [
                        "week_label",
                        "team",
                        "opponent",
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
                    "Site",
                    "Team Rating",
                    "Opponent Rating",
                    "Projected Spread",
                    "Favorite",
                    "Favorite Spread",
                    "Win Probability",
                ]
                st.dataframe(team_games, use_container_width=True, hide_index=True)

    with odds_tab:
        if odds.empty:
            render_missing_state(Path(odds_path), "Odds comparison file")
        else:
            odds_board = add_week_display_columns(odds)
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
            ]
            for column in numeric_columns:
                if column in odds_board.columns:
                    odds_board[column] = pd.to_numeric(odds_board[column], errors="coerce")
            if "market_status" not in odds_board.columns:
                odds_board["market_status"] = "open_market"

            live_odds = odds_board[odds_board["market_home_spread"].notna()].copy()
            no_current_odds = odds_board[odds_board["market_home_spread"].isna()].copy()
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            metric_col1.metric("Live Odds Games", f"{len(live_odds)}")
            metric_col2.metric("Completed No-Odds", f"{len(no_current_odds)}")
            metric_col3.metric("Largest Live Edge", f"{live_odds['absolute_edge_points'].max():.2f}" if not live_odds.empty else "N/A")

            filter_col1, filter_col2, filter_col3 = st.columns([1, 1.4, 2])
            available_weeks = sorted(int(week) for week in odds_board["display_week"].dropna().unique()) if "display_week" in odds_board.columns else []
            week_options = {f"Week {week}": week for week in available_weeks}
            with filter_col1:
                week_filter = st.selectbox("Week", ["All"] + list(week_options), index=0, key="odds_week_filter")
            with filter_col2:
                edge_range = st.slider(
                    "Edge range",
                    min_value=0.0,
                    max_value=50.0,
                    value=(2.5, 10.0),
                    step=0.5,
                    help="Very large edges are often data/model review candidates rather than clean value spots.",
                )
            with filter_col3:
                odds_search = st.text_input(
                    "Search odds board",
                    placeholder="Search by team, matchup, or edge side",
                    key="odds_search",
                ).strip().lower()

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
            if odds_search:
                filtered_odds = filtered_odds[
                    filtered_odds.apply(
                        lambda row: odds_search in str(row.get("home_team", "")).lower()
                        or odds_search in str(row.get("away_team", "")).lower()
                        or odds_search in str(row.get("edge_side", "")).lower(),
                        axis=1,
                    )
                ]

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
            filtered_odds["result"] = filtered_odds.apply(
                lambda row: (
                    f"{row.get('away_team')} {int(row.get('actual_away_points'))}, {row.get('home_team')} {int(row.get('actual_home_points'))}"
                    if pd.notna(row.get("actual_away_points")) and pd.notna(row.get("actual_home_points"))
                    else ""
                ),
                axis=1,
            )

            display = filtered_odds[
                [
                    "week_label",
                    "commence_time",
                    "matchup",
                    "market_status",
                    "edge_side",
                    "edge_display",
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
                "Market Status",
                "Model Edge Side",
                "Edge Points",
                "Model Line",
                "Market Line",
                "Result",
                "Books",
                "Market Total",
            ]
            st.dataframe(display, use_container_width=True, hide_index=True, height=520)

            with st.expander("Raw odds comparison"):
                st.dataframe(filtered_odds, use_container_width=True, hide_index=True)

    with review_tab:
        if weekly_review.empty or completed_review.empty:
            render_missing_state(Path(completed_review_path), "Completed games review file")
        else:
            weekly_results = add_week_display_columns(weekly_review)
            completed_games = add_week_display_columns(completed_review)
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
            st.dataframe(weekly_display, use_container_width=True, hide_index=True)

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

            available_review_weeks = sorted(int(week) for week in completed_games["display_week"].dropna().unique())
            review_week_options = {f"Week {week}": week for week in available_review_weeks}
            review_filter_col1, review_filter_col2 = st.columns([1, 2])
            with review_filter_col1:
                review_week_filter = st.selectbox("Week", ["All"] + list(review_week_options), index=0, key="results_review_week")
            with review_filter_col2:
                review_search = st.text_input(
                    "Search completed games",
                    placeholder="Search by team, matchup, or result",
                    key="results_review_search",
                ).strip().lower()

            filtered_review = completed_games.copy()
            if review_week_filter != "All":
                filtered_review = filtered_review[filtered_review["display_week"] == review_week_options[review_week_filter]]
            if review_search:
                filtered_review = filtered_review[
                    filtered_review.apply(
                        lambda row: review_search in str(row.get("matchup", "")).lower()
                        or review_search in str(row.get("winner_model_result", "")).lower()
                        or review_search in str(row.get("edge_result", "")).lower(),
                        axis=1,
                    )
                ]

            review_game_display = filtered_review[
                [
                    "week_label",
                    "matchup",
                    "score",
                    "model_line",
                    "market_line",
                    "actual_home_margin",
                    "absolute_model_error",
                    "absolute_market_error",
                    "winner_model_result",
                    "edge_result",
                ]
            ].copy()
            review_game_display.columns = [
                "Week",
                "Matchup",
                "Final Score",
                "Model Line",
                "Market Line",
                "Actual Home Margin",
                "Model Error",
                "Market Error",
                "Winner Pick",
                "Edge Result",
            ]
            st.dataframe(review_game_display, use_container_width=True, hide_index=True, height=520)

    with backtest_tab:
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
            st.line_chart(chart_df, use_container_width=True)
            st.dataframe(backtest, use_container_width=True, hide_index=True)

    with files_tab:
        st.write("These are the current file paths the app is reading.")
        st.code(
            "Ratings CSV: "
            f"{ratings_path}\nBacktest CSV: {backtest_path}\nProjected Win Totals CSV: {win_totals_path}\n"
            f"Projected Games CSV: {projected_games_path}\nSchedule Coverage CSV: {schedule_coverage_path}\n"
            f"Odds Comparison CSV: {odds_path}\nWeekly Results Review CSV: {weekly_review_path}\n"
            f"Completed Games Review CSV: {completed_review_path}\nExcel Workbook: {excel_path}",
            language="text",
        )
        excel_file = Path(excel_path)
        if uploaded_excel is not None:
            st.download_button(
                "Download Excel workbook",
                data=BytesIO(uploaded_excel.getvalue()),
                file_name=uploaded_excel.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        elif excel_file.exists():
            st.download_button(
                "Download Excel workbook",
                data=excel_file.read_bytes(),
                file_name=excel_file.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            render_missing_state(excel_file, "Excel workbook")


if __name__ == "__main__":
    main()

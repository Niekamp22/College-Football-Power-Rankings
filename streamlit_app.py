from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_BACKTEST_PATH = Path("output/backtests/weekly_backtest_2025_regular.csv")
DEFAULT_EXCEL_PATH = Path("output/power_ratings_final.xlsx")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def win_probability(spread: float, margin_std_dev: float = 16.0) -> float:
    z_score = spread / margin_std_dev
    return 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))


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

    ratings_path = st.sidebar.text_input("Ratings CSV", str(DEFAULT_RATINGS_PATH))
    backtest_path = st.sidebar.text_input("Backtest CSV", str(DEFAULT_BACKTEST_PATH))
    excel_path = st.sidebar.text_input("Excel Workbook", str(DEFAULT_EXCEL_PATH))

    ratings = load_csv(Path(ratings_path))
    backtest = load_csv(Path(backtest_path))

    if ratings.empty:
        render_missing_state(Path(ratings_path), "Ratings file")
        st.stop()

    ratings = ratings.sort_values("rating", ascending=False).reset_index(drop=True)
    ratings.index = ratings.index + 1

    top_row = ratings.iloc[0]
    st.markdown(
        f"""
        <div style="padding: 1rem 1.2rem; border-radius: 18px; background: linear-gradient(135deg, #14324a, #b6461d); color: white; margin-bottom: 1rem;">
          <div style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.12em; opacity: 0.85;">Current No. 1</div>
          <div style="font-size: 2rem; font-weight: 700;">{top_row['team']}</div>
          <div style="font-size: 1rem; opacity: 0.92;">Rating {top_row['rating']:.2f} • Record {top_row['record']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rankings_tab, matchup_tab, backtest_tab, files_tab = st.tabs(["Rankings", "Matchup", "Backtest", "Files"])

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
        col1, col2 = st.columns(2)
        with col1:
            team_a_name = st.selectbox("Team A", team_names, index=0)
        with col2:
            team_b_name = st.selectbox("Team B", team_names, index=1 if len(team_names) > 1 else 0)

        team_a = ratings[ratings["team"] == team_a_name].iloc[0]
        team_b = ratings[ratings["team"] == team_b_name].iloc[0]
        spread = float(team_a["rating"]) - float(team_b["rating"])
        team_a_prob = win_probability(spread)

        metric1, metric2, metric3 = st.columns(3)
        favorite_label = f"{team_a_name} -{abs(spread):.1f}" if spread >= 0 else f"{team_b_name} -{abs(spread):.1f}"
        metric1.metric("Projected Spread", favorite_label)
        metric2.metric(f"{team_a_name} Win %", f"{team_a_prob * 100:.1f}%")
        metric3.metric(f"{team_b_name} Win %", f"{(1 - team_a_prob) * 100:.1f}%")

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
            f"Ratings CSV: {ratings_path}\nBacktest CSV: {backtest_path}\nExcel Workbook: {excel_path}",
            language="text",
        )
        excel_file = Path(excel_path)
        if excel_file.exists():
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

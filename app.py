from __future__ import annotations

import streamlit as st

from app_data import load_csv
from ui_helpers import (
    format_eastern_time,
    format_percent,
    friendly_book_name,
    is_frozen_rating_source,
    default_week_index,
    summarize_completed_games,
    latest_snapshot_status,
    load_refresh_status,
    win_probability,
    site_adjusted_spread,
    add_week_display_columns,
    add_game_type_column,
    team_watchlist_label,
    summarize_team_betting,
    build_team_betting_summary,
    render_missing_state,
)


def main() -> None:
    st.set_page_config(
        page_title="College Football Power Ratings",
        page_icon="🏈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    if st.query_params.get("interface", "basic") == "interactive":
        from legacy_ui import render_legacy_interface

        render_legacy_interface()
    else:
        from recovery_ui import render_recovery_view

        render_recovery_view()


if __name__ == "__main__":
    main()

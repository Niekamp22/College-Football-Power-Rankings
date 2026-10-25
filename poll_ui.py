from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


def render_joshs_poll(season: int = 2026, root: Path = Path("output/polls")) -> None:
    st.subheader("Josh's Poll")
    st.caption("70% resume + 30% power. Wins, losses, and the opponents you beat determine the resume.")
    latest_path = root / f"joshs_poll_{season}.csv"
    if not latest_path.exists():
        st.info("Josh's Poll will appear after the next model refresh.")
        return
    season_root = root / str(season)
    archives = sorted(season_root.glob("week_*_poll.csv"), reverse=True)
    editions = {"Latest": None}
    editions.update({f"Through Week {int(path.stem.split('_')[1])}": path for path in archives})
    edition = st.selectbox("Poll edition", list(editions), key="josh_edition")
    archived = editions[edition]
    poll_path = archived or latest_path
    detail_path = archived.with_name(archived.name.replace("_poll.csv", "_games.csv")) if archived else root / f"joshs_poll_games_{season}.csv"
    metadata_path = archived.with_name(archived.name.replace("_poll.csv", "_metadata.json")) if archived else season_root / "latest_metadata.json"
    poll = pd.read_csv(poll_path)
    details = pd.read_csv(detail_path) if detail_path.exists() else pd.DataFrame()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    ranked = poll[poll["rank"].notna()].sort_values("rank")
    if ranked.empty:
        st.info("The first poll will be published when teams have completed games.")
        return
    through = int(ranked["through_week"].iloc[0])
    updated = pd.to_datetime(metadata.get("generated_at_utc"), utc=True, errors="coerce")
    updated_text = updated.tz_convert("America/New_York").strftime("%b %d, %I:%M %p ET") if pd.notna(updated) else "Unavailable"
    st.caption(f"{season} season, results through Week {through}. Updated {updated_text}. Opponents are evaluated as of this edition.")
    if through < 3:
        st.info("Early-season poll: a small number of results can cause large weekly moves.")
    leader = ranked.iloc[0]
    first, second, third = st.columns(3)
    first.metric("Josh's No. 1", leader["team"], str(leader["record"]), delta_color="off")
    second.metric("Poll score", f"{leader['poll_score']:.2f}")
    third.metric("Resume / power rank", f"{int(leader['resume_rank'])} / {int(leader['power_rank'])}")

    left, middle, right = st.columns([1, 2, 2])
    scope = left.selectbox("Show", ["Top 25", "All FBS teams"], key="josh_scope")
    conference = middle.selectbox("Conference", ["All conferences"] + sorted(poll["conference"].dropna().unique().tolist()), key="josh_conference")
    search = right.text_input("Find a team", placeholder="Team name", key="josh_search")
    board = poll.copy()
    if scope == "Top 25":
        board = board[board["rank"] <= 25]
    if conference != "All conferences":
        board = board[board["conference"].eq(conference)]
    if search:
        board = board[board["team"].str.contains(search, case=False, regex=False, na=False)]
    components = st.checkbox("Show score breakdown", key="josh_components")
    columns = {
        "rank": "Rank", "team": "Team", "conference": "Conference", "record": "Record",
        "movement": "Change", "poll_score": "Poll Score", "resume_rank": "Resume Rank",
        "power_rank": "Power Rank", "top_25_wins": "Top 25 Wins", "best_win": "Best Win",
    }
    if components:
        columns.update({"resume_score": "Resume Score", "power_score": "Power Score",
                        "resume_contribution": "Resume 70%", "power_contribution": "Power 30%",
                        "resume_raw": "Earned Credits", "head_to_head_note": "Head-to-Head"})
    st.dataframe(board[list(columns)].rename(columns=columns), hide_index=True, width="stretch", height=620,
                 column_config={name: st.column_config.NumberColumn(format="%.2f") for name in
                                ["Poll Score", "Resume Score", "Power Score", "Resume 70%", "Power 30%", "Earned Credits"]})
    st.caption("Change compares with the previous published week; blank means no earlier edition. Positive means a rise. "
               "Top 25 Wins uses opponents' power ranks in this edition. Head-to-head can reorder a close score group.")
    if board.empty:
        st.info("No teams match these filters. Choose All FBS teams to search outside the Top 25.")
    st.download_button("Download this poll", poll.to_csv(index=False).encode("utf-8"),
                       file_name=f"joshs_poll_{season}_through_week_{through}.csv", mime="text/csv", key="josh_download")

    st.markdown("#### Explore a team's resume")
    selected = st.selectbox("Team", ranked["team"].tolist(), key="josh_team")
    team = ranked[ranked["team"].eq(selected)].iloc[0]
    first, second, third, fourth = st.columns(4)
    first.metric("Record", team["record"])
    second.metric("Josh's rank", str(int(team["rank"])))
    third.metric("Best win", team["best_win"])
    fourth.metric("Worst loss", team["worst_loss"])
    st.write(f"Resume score **{team['resume_score']:.2f}** contributes **{team['resume_contribution']:.2f}** points. "
             f"Power score **{team['power_score']:.2f}** contributes **{team['power_contribution']:.2f}** points. "
             f"Combined score: **{team['poll_score']:.2f}**.")
    st.caption(f"{team['win_credits']:.2f} win credits minus {team['loss_penalties']:.2f} loss deductions "
               f"= {team['resume_raw']:.2f} earned resume credits. "
               f"Top 50 wins: {int(team['top_50_wins'])}. FCS wins: {int(team['fcs_wins'])}.")
    if pd.notna(team.get("head_to_head_note")) and team.get("head_to_head_note"):
        st.info(str(team["head_to_head_note"]))
    if not details.empty:
        team_games = details[details["team"].eq(selected)].sort_values("start_date")
        game_columns = {"display_week": "Week", "opponent": "Opponent", "site": "Site", "result": "Result",
                        "score": "Score", "opponent_classification": "Division", "opponent_record": "Opponent Record",
                        "opponent_power_rank": "Current Power Rank", "win_credit": "Win Credit",
                        "loss_penalty": "Loss Deduction", "resume_points": "Net Credits"}
        st.dataframe(team_games[list(game_columns)].rename(columns=game_columns), hide_index=True, width="stretch",
                     column_config={name: st.column_config.NumberColumn(format="%.2f")
                                    for name in ["Win Credit", "Loss Deduction", "Net Credits"]})
    else:
        st.info("Game detail is unavailable for this edition.")
    with st.expander("How Josh's Poll works"):
        st.markdown(
            "**Resume:** A win over an FBS team earns 1 credit plus a quality bonus of up to 2 credits. "
            "The bonus is `2 x opponent strength cubed`, where strength is the opponent's current power percentile "
            "from 0 to 1. A win over an FCS team earns just 0.05 credits.\n\n"
            "**Losses:** An FBS loss costs 5 credits plus up to 2 more for losing to a weak opponent "
            "(`5 + 2 x (1 - opponent strength) squared`). An FCS loss costs 8 credits. "
            "Wins accumulate, so byes add no credits. All completed season games in the published data count equally. "
            "There is no scoring-margin bonus or extra late-season penalty in the resume calculation.\n\n"
            "**70/30 blend:** The lowest and highest earned resume totals are scaled to 0 and 100; "
            "the same scaling is applied separately to power ratings. Equal values share a score. "
            "Josh's score is `0.70 x Resume Score + 0.30 x Power Score`. "
            "These are ranking scores, not win or betting probabilities.\n\n"
            "**Head-to-head:** Teams are grouped from highest score down, with no group spanning more than "
            "1.0 combined point. Direct results order teams within each group; circular results retain score order. "
            "The displayed weighted score remains unchanged.\n\n"
            "Opponent quality uses this edition's model, so an earlier win can gain or lose value. "
            "The power model considers performance and market information; that also informs opponent strength. "
            "Existing AP and CFP poll positions are not inputs to Josh's Poll. "
            "History begins with the first published edition, and earlier weeks are preserved as new editions are created."
        )

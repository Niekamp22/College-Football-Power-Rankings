from __future__ import annotations

import html
import json
import math
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import streamlit as st


OUTPUT = Path("output")
PAGES = {
    "rankings": "Rankings", "poll": "Josh's Poll", "matchup": "Matchup Lab",
    "weekly": "Weekly Board", "odds": "Betting Board", "bets": "Best Bet Tracker",
    "results": "Performance", "forecast": "Season Forecast",
}


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def read_csv(relative: str) -> pd.DataFrame:
    path = OUTPUT / relative
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def emit(value: str) -> None:
    st.markdown(value, unsafe_allow_html=True)


def select(name: str, label: str, values: list[str], default: str = "") -> str:
    current = st.query_params.get(name, default or (values[0] if values else ""))
    options = "".join(f'<option value="{escape(value)}"{" selected" if value == current else ""}>{escape(value)}</option>'
                      for value in values)
    return f'<label>{escape(label)}<select name="{escape(name)}">{options}</select></label>'


def entry(name: str, label: str, default: str = "", numeric: bool = False) -> str:
    value = st.query_params.get(name, default)
    kind = 'type="number" min="0" max="50" step="0.5"' if numeric else 'type="search"'
    return f'<label>{escape(label)}<input {kind} name="{escape(name)}" value="{escape(value)}"></label>'


def form(page: str, controls: list[str]) -> None:
    # Native HTML controls submit a normal GET; no Streamlit widget modules are needed.
    emit('<form class="recovery-form" method="get" target="_self" action="">'
         '<input type="hidden" name="interface" value="basic">'
         f'<input type="hidden" name="page" value="{escape(page)}">'
         + "".join(controls) + '<button type="submit">Apply</button></form>')


def table(frame: pd.DataFrame, columns: dict[str, str], decimals: list[str] | None = None) -> None:
    if frame.empty:
        emit('<p class="recovery-note">No rows match these filters.</p>')
        return
    visible = frame[[column for column in columns if column in frame.columns]].copy()
    for column in decimals or []:
        if column in visible:
            visible[column] = pd.to_numeric(visible[column], errors="coerce").map(
                lambda value: f"{value:.2f}" if pd.notna(value) else "N/A")
    for column in visible.select_dtypes(include="number"):
        if column not in (decimals or []) and visible[column].dropna().mod(1).eq(0).all():
            visible[column] = visible[column].astype("Int64")
    emit('<div class="recovery-table">' + visible.rename(columns=columns).to_html(
        index=False, escape=True, border=0, na_rep="N/A") + "</div>")


def team_filter(frame: pd.DataFrame, fields: list[str], parameter: str = "search") -> pd.DataFrame:
    query = st.query_params.get(parameter, "").strip()
    if not query:
        return frame
    mask = pd.Series(False, index=frame.index)
    for field in fields:
        if field in frame:
            mask |= frame[field].astype(str).str.contains(query, case=False, regex=False, na=False)
    return frame.loc[mask]


def eastern(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return timestamp.tz_convert("America/New_York").strftime("%a %b %d, %I:%M %p ET") if pd.notna(timestamp) else "TBD"


def show_rankings(ratings: pd.DataFrame) -> None:
    board = ratings.sort_values("rating", ascending=False).reset_index(drop=True)
    board.insert(0, "rank", range(1, len(board) + 1))
    form("rankings", [select("scope", "Show", ["Top 25", "All FBS teams"]), entry("search", "Find a team"),
                      select("conference", "Conference", ["All conferences"] + sorted(board.conference.dropna().unique()))])
    board = team_filter(board, ["team"])
    if st.query_params.get("scope", "Top 25") == "Top 25":
        board = board[board["rank"] <= 25]
    conference = st.query_params.get("conference", "All conferences")
    if conference != "All conferences":
        board = board[board.conference.eq(conference)]
    emit("<p>Ratings estimate neutral-field strength. A 10-point rating difference projects a 10-point margin.</p>")
    table(board, {"rank": "Rank", "team": "Team", "conference": "Conference", "record": "Record",
                  "rating": "Power", "football_rating": "Football", "market_rating": "Market",
                  "rating_confidence": "Confidence"}, ["rating", "football_rating", "market_rating"])


def show_poll() -> None:
    root = OUTPUT / "polls/2026"
    editions = {"Latest": OUTPUT / "polls/joshs_poll_2026.csv"}
    editions.update({f"Through Week {int(path.stem.split('_')[1])}": path
                     for path in sorted(root.glob("week_*_poll.csv"), reverse=True)})
    selected = st.query_params.get("edition", "Latest")
    path = editions.get(selected, editions["Latest"])
    if not path.exists():
        emit("<p>The poll will appear after the next refresh.</p>")
        return
    poll = pd.read_csv(path).sort_values("rank")
    latest = path == editions["Latest"]
    metadata_path = root / "latest_metadata.json" if latest else path.with_name(path.name.replace("_poll.csv", "_metadata.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    emit(f"<p><strong>{metadata['resume_weight']:.0%} resume + {metadata['power_weight']:.0%} power.</strong> "
         f"Results through Week {metadata['through_week']}. Updated {escape(eastern(metadata['generated_at_utc']))}.</p>")
    teams = poll["team"].tolist()
    form("poll", [select("edition", "Edition", list(editions)), select("scope", "Show", ["Top 25", "All FBS teams"]),
                  select("team", "Explore a team's resume", teams), entry("search", "Find a team")])
    board = team_filter(poll, ["team"])
    if st.query_params.get("scope", "Top 25") == "Top 25":
        board = board[board["rank"] <= 25]
    table(board, {"rank": "Rank", "team": "Team", "record": "Record", "poll_score": "Poll Score",
                  "movement": "Change", "resume_rank": "Resume Rank", "power_rank": "Power Rank",
                  "best_win": "Best Win", "worst_loss": "Worst Loss"}, ["poll_score"])
    chosen = st.query_params.get("team", teams[0])
    found = poll[poll["team"].eq(chosen)]
    if found.empty:
        return
    row = found.iloc[0]
    emit(f"<h3>{escape(chosen)}: {escape(row['record'])}</h3><p>Resume contribution "
         f"<strong>{row['resume_contribution']:.2f}</strong> + power contribution "
         f"<strong>{row['power_contribution']:.2f}</strong> = <strong>{row['poll_score']:.2f}</strong>.</p>")
    if pd.notna(row.get("head_to_head_note")) and row["head_to_head_note"]:
        emit(f"<p>{escape(row['head_to_head_note'])}</p>")
    detail_path = OUTPUT / "polls/joshs_poll_games_2026.csv" if latest else path.with_name(path.name.replace("_poll.csv", "_games.csv"))
    if detail_path.exists():
        details = pd.read_csv(detail_path)
        table(details[details["team"].eq(chosen)].sort_values("start_date"), {
            "display_week": "Week", "opponent": "Opponent", "site": "Site", "result": "Result", "score": "Score",
            "opponent_power_rank": "Opponent Power Rank", "win_credit": "Win Credits", "loss_penalty": "Loss Deduction",
            "resume_points": "Net Credits"}, ["win_credit", "loss_penalty", "resume_points"])


def show_matchup(ratings: pd.DataFrame) -> None:
    teams = ratings["team"].tolist()
    sites = ["Neutral", "Team A Home", "Team B Home"]
    form("matchup", [select("team_a", "Team A", teams), select("team_b", "Team B", teams, teams[min(1, len(teams) - 1)]),
                     select("site", "Game site", sites)])
    team_a, team_b = st.query_params.get("team_a", teams[0]), st.query_params.get("team_b", teams[min(1, len(teams) - 1)])
    lookup = ratings.set_index("team")["rating"]
    if team_a not in lookup or team_b not in lookup:
        emit("<p>Choose two teams from the list.</p>")
        return
    if team_a == team_b:
        emit("<p>Choose two different teams.</p>")
        return
    site = st.query_params.get("site", "Neutral")
    margin = float(lookup[team_a]) - float(lookup[team_b]) + (2.5 if site == "Team A Home" else -2.5 if site == "Team B Home" else 0.0)
    probability = 0.5 * (1 + math.erf(margin / (16 * math.sqrt(2))))
    favorite = team_a if margin >= 0 else team_b
    emit(f'<div class="recovery-summary"><h3>{escape(favorite)} -{abs(margin):.1f}</h3>'
         f'<p>{escape(team_a)} win probability: <strong>{probability:.1%}</strong><br>'
         f'{escape(team_b)} win probability: <strong>{1 - probability:.1%}</strong></p>'
         f'<p>{escape(site)}. Home field is 2.5 points.</p></div>')


def week_choices(frame: pd.DataFrame) -> list[str]:
    return [str(int(value)) for value in sorted(frame["display_week"].dropna().unique())]


def show_weekly() -> None:
    games = read_csv("projections/projected_games_2026.csv").drop_duplicates("game_id")
    weeks = week_choices(games)
    future = games[(games["status"] != "Final") & (pd.to_datetime(games["start_date"], utc=True) >= pd.Timestamp.now(tz="UTC"))]
    default = str(int(future["display_week"].min())) if not future.empty else weeks[-1]
    form("weekly", [select("week", "Week", weeks, default), entry("search", "Find a team")])
    week = st.query_params.get("week", default)
    board = team_filter(games[games["display_week"].astype(str).eq(week)], ["home_team", "away_team"]).copy()
    board["kickoff"] = board["start_date"].map(eastern)
    board["favorite_spread"] = -board["favorite_spread"].abs()
    board["home_probability"] = board["home_win_probability"].map(lambda value: f"{value:.1%}")
    table(board.sort_values("start_date"), {"kickoff": "Kickoff (Eastern)", "away_team": "Away", "home_team": "Home",
          "status": "Status", "favorite": "Model Favorite", "favorite_spread": "Model Spread",
          "home_probability": "Home Win Probability", "result": "Final Score"}, ["favorite_spread"])


def show_odds() -> None:
    board = read_csv("odds/ncaaf_game_odds_comparison.csv")
    board = board[board["market_status"].eq("open_market")].copy()
    if board.empty:
        emit("<p>No current market lines are published.</p>")
        return
    form("odds", [select("week", "Week", ["All"] + week_choices(board)), entry("search", "Find a team"),
                  entry("min_edge", "Minimum edge", "0", True), entry("max_edge", "Maximum edge", "50", True)])
    try:
        minimum, maximum = float(st.query_params.get("min_edge", "0")), float(st.query_params.get("max_edge", "50"))
        if not 0 <= minimum <= maximum <= 50:
            raise ValueError
    except ValueError:
        emit("<p>Choose an edge range between 0 and 50, with minimum no greater than maximum.</p>")
        return
    week = st.query_params.get("week", "All")
    if week != "All":
        board = board[board["display_week"].astype(str).eq(week)]
    board = team_filter(board, ["home_team", "away_team"])
    board = board[board["absolute_edge_points"].between(minimum, maximum)].sort_values("absolute_edge_points", ascending=False)
    board["kickoff"] = board["commence_time"].map(eastern)
    table(board, {"kickoff": "Kickoff (Eastern)", "away_team": "Away", "home_team": "Home", "model_favorite": "Model Winner",
                  "edge_side": "Spread Lean", "selected_best_spread": "Best Line", "selected_best_price": "Price",
                  "selected_best_book": "Book", "absolute_edge_points": "Edge", "book_count": "Books",
                  "betting_status": "Status", "edge_review_flag": "Review"}, ["selected_best_spread", "absolute_edge_points"])
    emit("<p>Board edges are model comparisons. Recorded best bets are shown separately in Best Bet Tracker.</p>")


def show_bets() -> None:
    bets = read_csv("best_bets/best_bet_ledger_2026.csv")
    graded = bets[bets["status"].eq("graded")]
    counts = graded["ats_result"].value_counts()
    emit(f'<div class="recovery-summary"><h3>{counts.get("win", 0)} wins, {counts.get("loss", 0)} losses, '
         f'{counts.get("push", 0)} pushes</h3><p>Season profit: <strong>{graded["units"].sum():+.2f} units</strong>.</p></div>')
    pending = bets[bets["status"].eq("pending")]
    emit("<h3>Upcoming locked picks</h3>")
    table(pending, {"week_label": "Week", "matchup": "Matchup", "pick_team": "Pick", "locked_spread": "Locked Line",
                   "locked_price": "Locked Price", "locked_book": "Book", "model_edge": "Edge at Selection"}, ["locked_spread", "model_edge"])
    for row in pending.itertuples():
        emit(f"<details><summary>{escape(row.matchup)}: reasoning</summary><p>{escape(row.reasoning)}</p></details>")
    emit("<h3>Graded picks</h3>")
    table(graded.sort_values(["display_week", "selection_rank"], ascending=[False, True]), {
        "week_label": "Week", "matchup": "Matchup", "pick_team": "Pick", "locked_spread": "Line",
        "final_score": "Final Score", "ats_result": "ATS Result", "units": "Units"}, ["locked_spread", "units"])


def show_results() -> None:
    weekly = read_csv("reviews/weekly_results_review_2026.csv")
    emit("<h3>Weekly model results</h3>")
    table(weekly, {"week_label": "Week", "rating_source": "Rating Source", "games": "Games",
                   "model_margin_mae": "Model Margin Error", "market_margin_mae": "Market Margin Error",
                   "model_winner_accuracy": "Winner Accuracy", "edge_right_side_rate": "Edge Right-Side Rate"},
          ["model_margin_mae", "market_margin_mae", "model_winner_accuracy", "edge_right_side_rate"])
    emit("<p>Accuracy and right-side rates are fractions: 0.75 means 75%. Frozen weekly snapshots measure predictions made before games.</p>")
    games = read_csv("reviews/completed_games_review_2026.csv")
    weeks = week_choices(games)
    form("results", [select("week", "Week", weeks, weeks[-1]), entry("search", "Find a team")])
    board = team_filter(games[games["display_week"].astype(str).eq(st.query_params.get("week", weeks[-1]))], ["home_team", "away_team"])
    table(board, {"away_team": "Away", "away_points": "Away Score", "home_team": "Home", "home_points": "Home Score",
                  "model_home_spread": "Model Home Spread", "market_home_spread": "Market Home Spread",
                  "edge_result": "Edge Result", "absolute_model_error": "Model Error", "rating_source": "Rating Source"},
          ["model_home_spread", "market_home_spread", "absolute_model_error"])


def render_recovery_view() -> None:
    emit("""<style>
    .block-container{max-width:1380px;padding-top:1.5rem} h1,h2,h3{color:#14324a}
    .recovery-nav{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0}
    .recovery-nav a{color:#14324a;background:#efe4d2;padding:.5rem .8rem;border-radius:8px;text-decoration:none}
    .recovery-nav a[aria-current=page]{color:white;background:#14324a}
    .recovery-form{display:flex;gap:1rem;flex-wrap:wrap;align-items:end;margin:1rem 0}
    .recovery-form label{display:flex;flex:1 1 160px;flex-direction:column;gap:.4rem;color:#14324a}
    .recovery-form input,.recovery-form select{font:inherit;width:100%;min-height:42px;box-sizing:border-box;border:1px solid #d7cbb8;border-radius:8px;padding:.5rem;background:#fffaf2;color:#1d2430}
    .recovery-form button{font:inherit;background:#a73e1d;color:white;border:0;border-radius:8px;padding:.7rem 1.2rem;cursor:pointer}
    .recovery-table{max-width:100%;overflow-x:auto;margin:1rem 0}.recovery-table table{width:100%;border-collapse:collapse;white-space:nowrap}
    .recovery-table th{text-align:left;background:#14324a;color:white;padding:.6rem}.recovery-table td{padding:.6rem;border-bottom:1px solid #dfd5c6}
    .recovery-summary{padding:1rem;background:#efe4d2;border-left:4px solid #a73e1d;border-radius:8px}
    details{margin:.7rem 0}summary{cursor:pointer;color:#14324a}.recovery-note{color:#536170}
    @media(max-width:650px){.block-container{padding:1rem}.recovery-form label{flex-basis:100%}.recovery-nav a{font-size:.9rem}.recovery-table td,.recovery-table th{padding:.5rem}}
    </style>""")
    emit("<h1>College Football Power Ratings</h1><p class='recovery-note'>Recovery view. Rankings, projections, and recorded bets use the latest published model data.</p>")
    status_path = OUTPUT / "refresh_status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        emit(f"<p>Updated {escape(eastern(status.get('generated_at_utc')))}. All kickoff times are Eastern.</p>")
    page = st.query_params.get("page", "rankings")
    if page not in PAGES:
        page = "rankings"
    links = []
    for key, title in PAGES.items():
        url = "?" + urlencode({"interface": "basic", "page": key})
        links.append(f'<a href="{escape(url)}" target="_self"{" aria-current=page" if page == key else ""}>{escape(title)}</a>')
    emit('<nav class="recovery-nav">' + "".join(links) + "</nav>")
    emit(f"<h2>{escape(PAGES[page])}</h2>")
    ratings = read_csv("cfbd_power_ratings_current.csv")
    if ratings.empty:
        emit("<p>The published ratings are unavailable.</p>")
        return
    if page == "rankings":
        show_rankings(ratings)
    elif page == "poll":
        show_poll()
    elif page == "matchup":
        show_matchup(ratings)
    elif page == "weekly":
        show_weekly()
    elif page == "odds":
        show_odds()
    elif page == "bets":
        show_bets()
    elif page == "results":
        show_results()
    elif page == "forecast":
        form("forecast", [entry("search", "Find a team")])
        totals = team_filter(read_csv("projections/projected_win_totals_2026.csv"), ["team"])
        table(totals.sort_values("projected_wins", ascending=False), {
            "team": "Team", "conference": "Conference", "actual_wins": "Wins", "actual_losses": "Losses",
            "projected_wins": "Projected Wins", "projected_losses": "Projected Losses",
            "remaining_games": "Remaining Games", "schedule_games": "Scheduled Games"}, ["projected_wins", "projected_losses"])
    emit('<p><a target="_blank" rel="noopener" href="https://raw.githubusercontent.com/Niekamp22/College-Football-Power-Rankings/main/output/power_ratings_master.xlsx">Download latest Excel workbook</a>'
         ' &nbsp; <a target="_self" href="?interface=interactive">Open full interface</a></p>')

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DEFAULT_ODDS_PATH = Path("output/odds/ncaaf_game_odds_comparison.csv")
DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_current.csv")
DEFAULT_CLV_PATH = Path("output/odds/clv_summary.csv")
DEFAULT_SCHEDULE_PATH = Path("data/cfbd/raw/2026/games.json")
DEFAULT_LEDGER_PATH = Path("output/best_bets/best_bet_ledger_2026.csv")

LEDGER_COLUMNS = [
    "season",
    "display_week",
    "week_label",
    "selection_rank",
    "event_id",
    "captured_at_utc",
    "kickoff_utc",
    "matchup",
    "away_team",
    "home_team",
    "pick_team",
    "opponent",
    "locked_spread",
    "locked_price",
    "locked_book",
    "model_fair_line",
    "model_edge",
    "candidate_score",
    "book_count",
    "line_shopping_gain",
    "reasoning",
    "status",
    "final_score",
    "picked_team_margin",
    "cover_margin",
    "ats_result",
    "closing_spread",
    "clv_points",
    "units",
    "cumulative_units",
]


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
        football_edge = float(home["football_rating"]) - float(away["football_rating"]) + home_field - market_margin
        market_component_edge = float(home["market_rating"]) - float(away["market_rating"]) + home_field - market_margin
        if not (direction * football_edge > 0 and direction * market_component_edge > 0):
            continue

        home_confidence = confidence_values.get(str(home.get("rating_confidence", "")), 0.4)
        away_confidence = confidence_values.get(str(away.get("rating_confidence", "")), 0.4)
        if min(home_confidence, away_confidence) < confidence_values["Medium"]:
            continue
        confidence_score = (home_confidence + away_confidence) / 2
        edge = float(game["absolute_edge_points"])
        edge_quality = max(0.0, 1.0 - abs(edge - 5.5) / 5.5)
        liquidity_score = min(float(game["book_count"]) / 8.0, 1.0)
        shopping_value = float(game["line_shopping_value"]) if pd.notna(game.get("line_shopping_value")) else 0.0
        shopping_score = min(max(shopping_value, 0.0) / 1.5, 1.0)
        max_market_gap = max(abs(float(home["market_gap"])), abs(float(away["market_gap"])))
        if max_market_gap >= 10.0:
            continue
        model_fair_line = float(game["model_home_spread"]) if str(game["edge_side"]) == home_team else -float(game["model_home_spread"])
        candidate_score = 30.0 * edge_quality + 25.0 + 15.0 * liquidity_score + 10.0 * shopping_score + 20.0 * confidence_score
        reasoning = (
            f"The model's fair line is {game['edge_side']} {model_fair_line:+.1f}, compared with the best available "
            f"{float(game['selected_best_spread']):+.1f}. The independent football rating and market-rating component "
            f"both support {game['edge_side']} against the consensus line. The price is available across "
            f"{int(float(game['book_count']))} tracked books, and line shopping improves the consensus spread by "
            f"{shopping_value:.2f} points."
        )

        rows.append(
            {
                "Event ID": str(game.get("event_id", "")),
                "Display Week": selected_week,
                "Week": f"Week {selected_week}",
                "Kickoff": game.get("commence_time", ""),
                "Matchup": f"{away_team} at {home_team}",
                "Home Team": home_team,
                "Away Team": away_team,
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
                "Caution": "Confirm injuries, weather, and the line before locking the pick.",
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Candidate Score", "Model Edge"], ascending=[False, False]).reset_index(drop=True)


def payout_units(price: int) -> float:
    return 100.0 / abs(price) if price < 0 else price / 100.0


def load_frame(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() and path.stat().st_size else pd.DataFrame()


def grade_ledger(ledger: pd.DataFrame, schedule_path: Path, clv_path: Path) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    schedule = json.loads(schedule_path.read_text(encoding="utf-8")) if schedule_path.exists() else []
    schedule_lookup = {
        (str(game.get("homeTeam", "")), str(game.get("awayTeam", ""))): game
        for game in schedule
    }
    clv = load_frame(clv_path)
    clv_lookup = clv.set_index("event_id").to_dict("index") if not clv.empty and "event_id" in clv.columns else {}

    graded = ledger.copy()
    for column in ["status", "final_score", "ats_result"]:
        graded[column] = graded[column].astype("object")
    for index, row in graded.iterrows():
        game = schedule_lookup.get((str(row["home_team"]), str(row["away_team"])), {})
        pick_home = str(row["pick_team"]) == str(row["home_team"])
        result = ""
        units = 0.0
        if game.get("completed") and game.get("homePoints") is not None and game.get("awayPoints") is not None:
            home_points = float(game["homePoints"])
            away_points = float(game["awayPoints"])
            picked_margin = home_points - away_points if pick_home else away_points - home_points
            cover_margin = picked_margin + float(row["locked_spread"])
            result = "win" if cover_margin > 0 else "loss" if cover_margin < 0 else "push"
            price = int(float(row["locked_price"]))
            units = payout_units(price) if result == "win" else -1.0 if result == "loss" else 0.0
            graded.at[index, "status"] = "graded"
            graded.at[index, "final_score"] = f"{row['away_team']} {int(away_points)}, {row['home_team']} {int(home_points)}"
            graded.at[index, "picked_team_margin"] = round(picked_margin, 2)
            graded.at[index, "cover_margin"] = round(cover_margin, 2)
            graded.at[index, "ats_result"] = result
            graded.at[index, "units"] = round(units, 3)
        else:
            graded.at[index, "status"] = "pending"
            graded.at[index, "units"] = 0.0

        clv_row = clv_lookup.get(str(row["event_id"]), {})
        closing = pd.to_numeric(pd.Series([clv_row.get("closing_side_spread")]), errors="coerce").iloc[0]
        if pd.notna(closing):
            if str(clv_row.get("edge_side", "")) != str(row["pick_team"]):
                closing = -float(closing)
            graded.at[index, "closing_spread"] = round(float(closing), 2)
            graded.at[index, "clv_points"] = round(float(row["locked_spread"]) - float(closing), 2)

    graded = graded.sort_values(["display_week", "selection_rank", "kickoff_utc"]).reset_index(drop=True)
    graded["cumulative_units"] = pd.to_numeric(graded["units"], errors="coerce").fillna(0).cumsum().round(3)
    return graded.reindex(columns=LEDGER_COLUMNS)


def capture_current_week(ledger: pd.DataFrame, odds: pd.DataFrame, ratings: pd.DataFrame, season: int, top: int) -> pd.DataFrame:
    shortlist = build_podcast_shortlist(odds, ratings)
    if shortlist.empty:
        return ledger

    week = int(shortlist.iloc[0]["Display Week"])
    if not ledger.empty and (pd.to_numeric(ledger["display_week"], errors="coerce") == week).any():
        return ledger

    now = datetime.now(timezone.utc)
    kickoff = pd.to_datetime(shortlist["Kickoff"], errors="coerce", utc=True)
    shortlist = shortlist[kickoff > now].head(top)
    new_rows: list[dict[str, object]] = []
    captured_at = now.isoformat(timespec="seconds")
    for rank, (_, pick) in enumerate(shortlist.iterrows(), start=1):
        opponent = pick["Away Team"] if pick["Model Lean"] == pick["Home Team"] else pick["Home Team"]
        new_rows.append(
            {
                "season": season,
                "display_week": week,
                "week_label": pick["Week"],
                "selection_rank": rank,
                "event_id": pick["Event ID"],
                "captured_at_utc": captured_at,
                "kickoff_utc": pick["Kickoff"],
                "matchup": pick["Matchup"],
                "away_team": pick["Away Team"],
                "home_team": pick["Home Team"],
                "pick_team": pick["Model Lean"],
                "opponent": opponent,
                "locked_spread": pick["Best Line"],
                "locked_price": pick["Price"],
                "locked_book": pick["Book"],
                "model_fair_line": pick["Model Fair Line"],
                "model_edge": pick["Model Edge"],
                "candidate_score": pick["Candidate Score"],
                "book_count": pick["Books"],
                "line_shopping_gain": pick["Line Shopping Gain"],
                "reasoning": pick["Reasoning"],
                "status": "pending",
                "units": 0.0,
            }
        )
    if not new_rows:
        return ledger
    return pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True).reindex(columns=LEDGER_COLUMNS)


def update_ledger(
    odds_path: Path = DEFAULT_ODDS_PATH,
    ratings_path: Path = DEFAULT_RATINGS_PATH,
    schedule_path: Path = DEFAULT_SCHEDULE_PATH,
    clv_path: Path = DEFAULT_CLV_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    season: int = 2026,
    top: int = 4,
) -> pd.DataFrame:
    ledger = load_frame(ledger_path).reindex(columns=LEDGER_COLUMNS)
    ledger = grade_ledger(ledger, schedule_path, clv_path)
    ledger = capture_current_week(ledger, load_frame(odds_path), load_frame(ratings_path), season, top)
    ledger = grade_ledger(ledger, schedule_path, clv_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(ledger_path, index=False)
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze and grade the model's weekly best-bet shortlist.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--top", type=int, default=4)
    args = parser.parse_args()
    ledger = update_ledger(season=args.season, top=args.top)
    pending = int(ledger["status"].eq("pending").sum()) if not ledger.empty else 0
    graded = int(ledger["status"].eq("graded").sum()) if not ledger.empty else 0
    print(f"Saved {len(ledger)} best bets to {DEFAULT_LEDGER_PATH} ({graded} graded, {pending} pending).")


if __name__ == "__main__":
    main()

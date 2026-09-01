from __future__ import annotations

import argparse
import csv
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_weeks import display_week_for_game, week_label
from project_win_totals import HOME_FIELD_ADVANTAGE, FCS_BASELINE_RATING, parse_float


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_SCHEDULE_PATH = Path("data/cfbd/raw/2026/games.json")
DEFAULT_OUTPUT_ROOT = Path("output/odds")
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
NCAAF_SPORT_KEY = "americanfootball_ncaaf"

TEAM_ALIASES = {
    "houston baptist": "Houston Christian",
    "houston baptist huskies": "Houston Christian",
    "sam houston state": "Sam Houston",
    "sam houston state bearkats": "Sam Houston",
    "hawaii": "Hawai'i",
    "hawaii rainbow warriors": "Hawai'i",
    "san jose state": "San José State",
    "san jose state spartans": "San José State",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch live NCAAF odds and compare them to model projections.")
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS_PATH)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--api-key-env", default="ODDS_API_KEY", help="Environment variable containing The Odds API key.")
    parser.add_argument("--regions", default="us")
    parser.add_argument("--bookmakers", help="Optional comma-separated bookmaker keys, for example fanduel,draftkings.")
    parser.add_argument(
        "--include-title-futures",
        action="store_true",
        help="Also fetch NCAAF national title futures. Disabled by default.",
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Use the latest saved raw odds file instead of calling the API.")
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    base_fields = list(rows[0].keys())
    extra_fields = sorted({key for row in rows for key in row.keys()} - set(base_fields))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=base_fields + extra_fields)
        writer.writeheader()
        writer.writerows(rows)


def fetch_json(path: str, api_key: str, params: dict[str, str]) -> Any:
    query = urllib.parse.urlencode({"apiKey": api_key, **params})
    request = urllib.request.Request(f"{ODDS_API_BASE_URL}{path}?{query}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def timestamp_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def normalize_team_name(name: str) -> str:
    normalized = name.lower()
    normalized = normalized.replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def build_team_lookup(team_names: set[str]) -> dict[str, str]:
    lookup = {normalize_team_name(team): team for team in team_names}
    for team in team_names:
        normalized = normalize_team_name(team)
        lookup.setdefault(normalized.replace("state", "st"), team)
        lookup.setdefault(normalized.replace("st", "state"), team)
    return lookup


def resolve_team(api_name: str, team_lookup: dict[str, str]) -> str | None:
    normalized = normalize_team_name(api_name)
    if normalized in TEAM_ALIASES:
        return TEAM_ALIASES[normalized]
    if normalized in team_lookup:
        return team_lookup[normalized]

    candidates = [
        team
        for key, team in team_lookup.items()
        if normalized.startswith(f"{key} ") or normalized == key
    ]
    unique = sorted(set(candidates), key=len, reverse=True)
    return unique[0] if len(unique) == 1 else None


def market_by_key(bookmaker: dict[str, Any], market_key: str) -> dict[str, Any] | None:
    for market in bookmaker.get("markets", []):
        if market.get("key") == market_key:
            return market
    return None


def home_spread_for_book(bookmaker: dict[str, Any], home_api_name: str) -> tuple[float | None, int | None]:
    market = market_by_key(bookmaker, "spreads")
    if not market:
        return None, None
    for outcome in market.get("outcomes", []):
        if outcome.get("name") == home_api_name and outcome.get("point") is not None:
            return float(outcome["point"]), outcome.get("price")
    return None, None


def total_for_book(bookmaker: dict[str, Any]) -> tuple[float | None, int | None, int | None]:
    market = market_by_key(bookmaker, "totals")
    if not market:
        return None, None, None
    over_price = None
    under_price = None
    total = None
    for outcome in market.get("outcomes", []):
        if outcome.get("point") is not None:
            total = float(outcome["point"])
        if outcome.get("name") == "Over":
            over_price = outcome.get("price")
        if outcome.get("name") == "Under":
            under_price = outcome.get("price")
    return total, over_price, under_price


def h2h_price_for_book(bookmaker: dict[str, Any], home_api_name: str, away_api_name: str) -> tuple[int | None, int | None]:
    market = market_by_key(bookmaker, "h2h")
    if not market:
        return None, None
    home_price = None
    away_price = None
    for outcome in market.get("outcomes", []):
        if outcome.get("name") == home_api_name:
            home_price = outcome.get("price")
        if outcome.get("name") == away_api_name:
            away_price = outcome.get("price")
    return home_price, away_price


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_schedule_lookup(schedule_games: list[dict[str, Any]], team_lookup: dict[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for game in schedule_games:
        home_team = game.get("homeTeam")
        away_team = game.get("awayTeam")
        if not home_team or not away_team:
            continue
        resolved_home = resolve_team(home_team, team_lookup) or home_team
        resolved_away = resolve_team(away_team, team_lookup) or away_team
        lookup[(resolved_home, resolved_away)] = game
    return lookup


def compare_game_odds(
    odds_rows: list[dict[str, Any]],
    ratings_rows: list[dict[str, Any]],
    schedule_games: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ratings = {row["team"]: parse_float(row["rating"]) for row in ratings_rows}
    team_names = set(ratings) | {game.get("homeTeam", "") for game in schedule_games} | {game.get("awayTeam", "") for game in schedule_games}
    team_names.discard("")
    team_lookup = build_team_lookup(team_names)
    schedule_lookup = build_schedule_lookup(schedule_games, team_lookup)

    comparison_rows: list[dict[str, Any]] = []
    for event in odds_rows:
        home_api_name = event.get("home_team")
        away_api_name = event.get("away_team")
        if not home_api_name or not away_api_name:
            continue

        home_team = resolve_team(home_api_name, team_lookup)
        away_team = resolve_team(away_api_name, team_lookup)
        if not home_team or not away_team:
            continue

        schedule_game = schedule_lookup.get((home_team, away_team), {})
        home_rating = ratings.get(home_team)
        away_rating = ratings.get(away_team)
        if home_rating is None or away_rating is None:
            continue

        home_field = 0.0 if schedule_game.get("neutralSite") else HOME_FIELD_ADVANTAGE
        model_home_margin = home_rating - away_rating + home_field
        model_home_spread = -model_home_margin

        spread_values: list[float] = []
        total_values: list[float] = []
        book_columns: dict[str, Any] = {}
        for bookmaker in event.get("bookmakers", []):
            book_key = bookmaker.get("key", "")
            home_spread, home_spread_price = home_spread_for_book(bookmaker, home_api_name)
            total, over_price, under_price = total_for_book(bookmaker)
            home_ml, away_ml = h2h_price_for_book(bookmaker, home_api_name, away_api_name)

            if home_spread is not None:
                spread_values.append(home_spread)
                book_columns[f"{book_key}_home_spread"] = home_spread
                book_columns[f"{book_key}_home_spread_price"] = home_spread_price
            if total is not None:
                total_values.append(total)
                book_columns[f"{book_key}_total"] = total
                book_columns[f"{book_key}_over_price"] = over_price
                book_columns[f"{book_key}_under_price"] = under_price
            if home_ml is not None or away_ml is not None:
                book_columns[f"{book_key}_home_moneyline"] = home_ml
                book_columns[f"{book_key}_away_moneyline"] = away_ml

        market_home_spread = average(spread_values)
        if market_home_spread is None:
            continue

        market_home_margin = -market_home_spread
        model_edge_home_points = model_home_margin - market_home_margin
        model_favorite = home_team if model_home_margin >= 0 else away_team
        market_favorite = home_team if market_home_margin >= 0 else away_team

        comparison_rows.append(
            {
                "event_id": event.get("id"),
                "commence_time": event.get("commence_time"),
                "week": schedule_game.get("week", ""),
                "display_week": display_week_for_game(schedule_game) if schedule_game else "",
                "week_label": week_label(display_week_for_game(schedule_game)) if schedule_game else "",
                "home_team": home_team,
                "away_team": away_team,
                "neutral_site": bool(schedule_game.get("neutralSite", False)),
                "book_count": len(event.get("bookmakers", [])),
                "model_home_margin": round(model_home_margin, 2),
                "model_home_spread": round(model_home_spread, 2),
                "market_home_spread": round(market_home_spread, 2),
                "market_home_margin": round(market_home_margin, 2),
                "edge_home_points": round(model_edge_home_points, 2),
                "edge_side": home_team if model_edge_home_points > 0 else away_team,
                "absolute_edge_points": round(abs(model_edge_home_points), 2),
                "model_favorite": model_favorite,
                "market_favorite": market_favorite,
                "market_total": round(average(total_values), 2) if total_values else "",
                **book_columns,
            }
        )

    comparison_rows.sort(key=lambda row: (-float(row["absolute_edge_points"]), str(row["commence_time"])))
    return comparison_rows


def main() -> None:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    if args.skip_fetch:
        raw_files = sorted(args.output_root.glob("ncaaf_game_odds_*.json"))
        if not raw_files:
            raise SystemExit("No saved raw odds files found. Run without --skip-fetch first.")
        odds_rows = load_json(raw_files[-1])
    else:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise SystemExit(f"Set {args.api_key_env} before running this script.")

        params = {
            "regions": args.regions,
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if args.bookmakers:
            params["bookmakers"] = args.bookmakers

        odds_rows = fetch_json(f"/sports/{NCAAF_SPORT_KEY}/odds", api_key, params)
        raw_path = args.output_root / f"ncaaf_game_odds_{timestamp_label()}.json"
        raw_path.write_text(json.dumps(odds_rows, indent=2), encoding="utf-8")
        print(f"Saved raw game odds to {raw_path}")

        if args.include_title_futures:
            futures_rows = fetch_json(
                "/sports/americanfootball_ncaaf_championship_winner/odds",
                api_key,
                {
                    "regions": args.regions,
                    "markets": "outrights",
                    "oddsFormat": "american",
                    "dateFormat": "iso",
                },
            )
            futures_path = args.output_root / f"ncaaf_title_futures_{timestamp_label()}.json"
            futures_path.write_text(json.dumps(futures_rows, indent=2), encoding="utf-8")
            print(f"Saved raw title futures to {futures_path}")

    ratings_rows = load_csv(args.ratings)
    schedule_games = load_json(args.schedule)
    comparison_rows = compare_game_odds(odds_rows, ratings_rows, schedule_games)
    comparison_path = args.output_root / "ncaaf_game_odds_comparison.csv"
    write_csv(comparison_path, comparison_rows)
    print(f"Saved game odds comparison to {comparison_path}")
    print(f"Compared {len(comparison_rows)} games.")


if __name__ == "__main__":
    main()

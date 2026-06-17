from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


DEFAULT_INPUT_ROOT = Path("data/cfbd/raw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect downloaded CFBD data and summarize available ranking features.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    return parser.parse_args()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_games(games: list[dict]) -> None:
    completed = sum(1 for game in games if game.get("completed"))
    fbs_vs_fbs = sum(
        1
        for game in games
        if game.get("homeClassification") == "fbs" and game.get("awayClassification") == "fbs"
    )
    season_types = Counter(game.get("seasonType") for game in games)
    weeks = sorted({game.get("week") for game in games if game.get("week") is not None})
    conferences = Counter()
    for game in games:
        if game.get("homeConference"):
            conferences[game["homeConference"]] += 1
        if game.get("awayConference"):
            conferences[game["awayConference"]] += 1

    elo_ready = sum(1 for game in games if game.get("homePregameElo") is not None and game.get("awayPregameElo") is not None)

    print("Games")
    print(f"  Total games: {len(games)}")
    print(f"  Completed games: {completed}")
    print(f"  FBS vs FBS games: {fbs_vs_fbs}")
    print(f"  Games with CFBD pregame Elo: {elo_ready}")
    print(f"  Season types: {dict(season_types)}")
    print(f"  Weeks present: {weeks[0]}-{weeks[-1]}" if weeks else "  Weeks present: none")
    print(f"  Top conferences by appearances: {conferences.most_common(10)}")
    print()


def summarize_lines(lines: list[dict]) -> None:
    with_market = sum(1 for game in lines if game.get("lines"))
    providers = Counter()
    spread_count = 0
    total_count = 0
    for game in lines:
        for line in game.get("lines", []):
            provider = line.get("provider")
            if provider:
                providers[provider] += 1
            if line.get("spread") is not None:
                spread_count += 1
            if line.get("overUnder") is not None:
                total_count += 1

    print("Lines")
    print(f"  Games with lines: {with_market}")
    print(f"  Individual line entries with spread: {spread_count}")
    print(f"  Individual line entries with total: {total_count}")
    print(f"  Top providers: {providers.most_common(10)}")
    print()


def summarize_advanced_stats(stats: list[dict]) -> None:
    offense_keys = sorted(stats[0]["offense"].keys()) if stats else []
    defense_keys = sorted(stats[0]["defense"].keys()) if stats else []
    print("Advanced Team Stats")
    print(f"  Teams: {len(stats)}")
    print(f"  Offense keys: {offense_keys}")
    print(f"  Defense keys: {defense_keys}")
    print()


def summarize_wepa(wepa: list[dict]) -> None:
    top_level_keys = sorted(wepa[0].keys()) if wepa else []
    print("WEPA")
    print(f"  Teams: {len(wepa)}")
    print(f"  Keys: {top_level_keys}")
    print()


def summarize_talent(talent: list[dict]) -> None:
    talent_values = [entry["talent"] for entry in talent if entry.get("talent") is not None]
    print("Talent")
    print(f"  Teams: {len(talent)}")
    if talent_values:
        print(f"  Talent range: {min(talent_values):.2f} to {max(talent_values):.2f}")
    print()


def summarize_rankings(rankings: list[dict]) -> None:
    poll_names = Counter()
    weeks = []
    for week in rankings:
        weeks.append(week.get("week"))
        for poll in week.get("polls", []):
            if poll.get("poll"):
                poll_names[poll["poll"]] += 1

    print("Rankings")
    print(f"  Weekly ranking snapshots: {len(rankings)}")
    print(f"  Weeks present: {min(weeks)}-{max(weeks)}" if weeks else "  Weeks present: none")
    print(f"  Polls available: {poll_names.most_common(10)}")
    print()


def main() -> None:
    args = parse_args()
    base = args.input_root / str(args.year)

    games = load_json(base / "games.json")
    lines = load_json(base / "lines.json")
    advanced = load_json(base / "advanced_team_stats.json")
    wepa = load_json(base / "wepa.json")
    talent = load_json(base / "talent.json")
    rankings = load_json(base / "rankings.json")

    print(f"CFBD summary for {args.year}")
    print()
    summarize_games(games)
    summarize_lines(lines)
    summarize_advanced_stats(advanced)
    summarize_wepa(wepa)
    summarize_talent(talent)
    summarize_rankings(rankings)


if __name__ == "__main__":
    main()

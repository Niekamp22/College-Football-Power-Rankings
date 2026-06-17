from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT_ROOT = Path("data/cfbd/raw")
DEFAULT_OUTPUT_ROOT = Path("data/cfbd/processed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a flattened team feature table from downloaded CFBD data.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def flatten_poll_positions(rankings: list[dict[str, Any]]) -> dict[str, dict[str, int | None]]:
    poll_snapshots: dict[str, dict[str, int | None]] = defaultdict(dict)

    for snapshot in sorted(rankings, key=lambda item: item.get("week", 0)):
        for poll in snapshot.get("polls", []):
            poll_name = poll.get("poll")
            if poll_name not in {"AP Top 25", "Coaches Poll", "Playoff Committee Rankings"}:
                continue

            label = {
                "AP Top 25": "ap",
                "Coaches Poll": "coaches",
                "Playoff Committee Rankings": "cfp",
            }[poll_name]

            ranked_teams = {rank["school"]: rank["rank"] for rank in poll.get("ranks", [])}
            for team, rank in ranked_teams.items():
                if f"{label}_preseason_rank" not in poll_snapshots[team]:
                    poll_snapshots[team][f"{label}_preseason_rank"] = rank
                poll_snapshots[team][f"{label}_latest_rank"] = rank

    return poll_snapshots


def summarize_lines(lines: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, float]]:
    line_lookup: dict[tuple[str, str, int], dict[str, float]] = {}

    for game in lines:
        providers = game.get("lines", [])
        spreads = [provider.get("spread") for provider in providers if provider.get("spread") is not None]
        totals = [provider.get("overUnder") for provider in providers if provider.get("overUnder") is not None]

        line_lookup[(game["homeTeam"], game["awayTeam"], game["week"])] = {
            "avg_home_spread": average([float(spread) for spread in spreads]),
            "avg_over_under": average([float(total) for total in totals]),
            "line_count": float(len(providers)),
        }

    return line_lookup


def build_game_features(
    games: list[dict[str, Any]],
    line_lookup: dict[tuple[str, str, int], dict[str, float]],
) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    completed_games = [
        game
        for game in games
        if game.get("completed") and game.get("homePoints") is not None and game.get("awayPoints") is not None
    ]
    completed_games.sort(key=lambda game: (int(game.get("week") or 0), game.get("startDate") or "", game.get("id") or 0))
    max_week = max((int(game.get("week") or 0) for game in completed_games), default=0)

    def ensure_team(
        team: str,
        team_id: int | None,
        conference: str | None,
        classification: str | None,
    ) -> dict[str, Any]:
        if team not in features:
            features[team] = {
                "team": team,
                "team_id": team_id or "",
                "conference": conference or "",
                "classification": classification or "",
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "fbs_games": 0,
                "fbs_wins": 0,
                "fbs_losses": 0,
                "points_for": 0,
                "points_against": 0,
                "margin_sum": 0,
                "fbs_margin_sum": 0,
                "opponent_pregame_elo_sum": 0.0,
                "fbs_opponent_pregame_elo_sum": 0.0,
                "opponent_postgame_elo_sum": 0.0,
                "fbs_opponent_postgame_elo_sum": 0.0,
                "recent_weight_sum": 0.0,
                "recent_fbs_weight_sum": 0.0,
                "recent_win_weight_sum": 0.0,
                "recent_fbs_win_weight_sum": 0.0,
                "recent_margin_weight_sum": 0.0,
                "recent_fbs_margin_weight_sum": 0.0,
                "recent_cover_weight_sum": 0.0,
                "recent_cover_margin_weight_sum": 0.0,
                "pregame_elo_values": [],
                "postgame_elo_values": [],
                "latest_team_postgame_elo": 0.0,
                "latest_game_week": 0,
                "line_count_sum": 0.0,
                "games_with_lines": 0,
                "spread_values": [],
                "spread_delta_values": [],
                "total_values": [],
            }
        return features[team]

    for game in completed_games:
        game_week = int(game.get("week") or 0)
        recency_weight = 0.85 ** max(0, max_week - game_week)

        home_team = ensure_team(
            game["homeTeam"],
            game.get("homeId"),
            game.get("homeConference"),
            game.get("homeClassification"),
        )
        away_team = ensure_team(
            game["awayTeam"],
            game.get("awayId"),
            game.get("awayConference"),
            game.get("awayClassification"),
        )

        home_points = int(game["homePoints"])
        away_points = int(game["awayPoints"])
        margin = home_points - away_points
        fbs_vs_fbs = game.get("homeClassification") == "fbs" and game.get("awayClassification") == "fbs"

        for team_features, points_for, points_against, team_margin, win, team_pregame_elo, team_postgame_elo, opp_pregame_elo, opp_postgame_elo in (
            (
                home_team,
                home_points,
                away_points,
                margin,
                home_points > away_points,
                game.get("homePregameElo"),
                game.get("homePostgameElo"),
                game.get("awayPregameElo"),
                game.get("awayPostgameElo"),
            ),
            (
                away_team,
                away_points,
                home_points,
                -margin,
                away_points > home_points,
                game.get("awayPregameElo"),
                game.get("awayPostgameElo"),
                game.get("homePregameElo"),
                game.get("homePostgameElo"),
            ),
        ):
            team_features["games_played"] += 1
            team_features["wins"] += int(win)
            team_features["losses"] += int(not win)
            team_features["points_for"] += points_for
            team_features["points_against"] += points_against
            team_features["margin_sum"] += team_margin
            team_features["recent_weight_sum"] += recency_weight
            team_features["recent_win_weight_sum"] += recency_weight * int(win)
            team_features["recent_margin_weight_sum"] += recency_weight * team_margin

            if team_pregame_elo is not None:
                team_features["pregame_elo_values"].append(float(team_pregame_elo))
            if team_postgame_elo is not None:
                team_features["postgame_elo_values"].append(float(team_postgame_elo))
                if game_week >= team_features["latest_game_week"]:
                    team_features["latest_game_week"] = game_week
                    team_features["latest_team_postgame_elo"] = float(team_postgame_elo)
            if opp_pregame_elo is not None:
                team_features["opponent_pregame_elo_sum"] += float(opp_pregame_elo)
            if opp_postgame_elo is not None:
                team_features["opponent_postgame_elo_sum"] += float(opp_postgame_elo)

            if fbs_vs_fbs:
                team_features["fbs_games"] += 1
                team_features["fbs_wins"] += int(win)
                team_features["fbs_losses"] += int(not win)
                team_features["fbs_margin_sum"] += team_margin
                team_features["recent_fbs_weight_sum"] += recency_weight
                team_features["recent_fbs_win_weight_sum"] += recency_weight * int(win)
                team_features["recent_fbs_margin_weight_sum"] += recency_weight * team_margin
                if opp_pregame_elo is not None:
                    team_features["fbs_opponent_pregame_elo_sum"] += float(opp_pregame_elo)
                if opp_postgame_elo is not None:
                    team_features["fbs_opponent_postgame_elo_sum"] += float(opp_postgame_elo)

        line_data = line_lookup.get((game["homeTeam"], game["awayTeam"], game["week"]))
        if line_data:
            home_cover_margin = margin + line_data["avg_home_spread"]
            away_cover_margin = -home_cover_margin
            for team_features, team_spread, team_cover_margin in (
                (home_team, line_data["avg_home_spread"], home_cover_margin),
                (away_team, -line_data["avg_home_spread"], away_cover_margin),
            ):
                team_features["games_with_lines"] += 1
                team_features["recent_cover_weight_sum"] += recency_weight
                team_features["recent_cover_margin_weight_sum"] += recency_weight * team_cover_margin
                team_features["line_count_sum"] += line_data["line_count"]
                team_features["spread_values"].append(float(team_spread))
                team_features["spread_delta_values"].append(float(team_cover_margin))
                if line_data["avg_over_under"]:
                    team_features["total_values"].append(float(line_data["avg_over_under"]))

    for team, team_features in features.items():
        games_played = team_features["games_played"]
        fbs_games = team_features["fbs_games"]
        games_with_lines = team_features["games_with_lines"]

        team_features["win_pct"] = round(safe_divide(team_features["wins"], games_played), 4)
        team_features["fbs_win_pct"] = round(safe_divide(team_features["fbs_wins"], fbs_games), 4)
        team_features["avg_points_for"] = round(safe_divide(team_features["points_for"], games_played), 3)
        team_features["avg_points_against"] = round(safe_divide(team_features["points_against"], games_played), 3)
        team_features["avg_margin"] = round(safe_divide(team_features["margin_sum"], games_played), 3)
        team_features["fbs_avg_margin"] = round(safe_divide(team_features["fbs_margin_sum"], fbs_games), 3)
        team_features["recent_win_pct"] = round(
            safe_divide(team_features["recent_win_weight_sum"], team_features["recent_weight_sum"]),
            4,
        )
        team_features["recent_fbs_win_pct"] = round(
            safe_divide(team_features["recent_fbs_win_weight_sum"], team_features["recent_fbs_weight_sum"]),
            4,
        )
        team_features["recent_avg_margin"] = round(
            safe_divide(team_features["recent_margin_weight_sum"], team_features["recent_weight_sum"]),
            3,
        )
        team_features["recent_fbs_avg_margin"] = round(
            safe_divide(team_features["recent_fbs_margin_weight_sum"], team_features["recent_fbs_weight_sum"]),
            3,
        )
        team_features["recent_avg_cover_margin"] = round(
            safe_divide(team_features["recent_cover_margin_weight_sum"], team_features["recent_cover_weight_sum"]),
            3,
        )
        team_features["avg_team_pregame_elo"] = round(average(team_features["pregame_elo_values"]), 3)
        team_features["avg_team_postgame_elo"] = round(average(team_features["postgame_elo_values"]), 3)
        team_features["latest_team_postgame_elo"] = round(float(team_features["latest_team_postgame_elo"]), 3)
        team_features["avg_opponent_pregame_elo"] = round(
            safe_divide(team_features["opponent_pregame_elo_sum"], games_played), 3
        )
        team_features["avg_opponent_postgame_elo"] = round(
            safe_divide(team_features["opponent_postgame_elo_sum"], games_played), 3
        )
        team_features["fbs_avg_opponent_pregame_elo"] = round(
            safe_divide(team_features["fbs_opponent_pregame_elo_sum"], fbs_games), 3
        )
        team_features["fbs_avg_opponent_postgame_elo"] = round(
            safe_divide(team_features["fbs_opponent_postgame_elo_sum"], fbs_games), 3
        )
        team_features["avg_closing_spread"] = round(average(team_features["spread_values"]), 3)
        team_features["avg_cover_margin"] = round(average(team_features["spread_delta_values"]), 3)
        team_features["avg_closing_total"] = round(average(team_features["total_values"]), 3)
        team_features["avg_lines_per_game"] = round(safe_divide(team_features["line_count_sum"], games_with_lines), 3)

        del team_features["pregame_elo_values"]
        del team_features["postgame_elo_values"]
        del team_features["spread_values"]
        del team_features["spread_delta_values"]
        del team_features["total_values"]
        del team_features["recent_weight_sum"]
        del team_features["recent_fbs_weight_sum"]
        del team_features["recent_win_weight_sum"]
        del team_features["recent_fbs_win_weight_sum"]
        del team_features["recent_margin_weight_sum"]
        del team_features["recent_fbs_margin_weight_sum"]
        del team_features["recent_cover_weight_sum"]
        del team_features["recent_cover_margin_weight_sum"]
        del team_features["latest_game_week"]

    return features


def apply_advanced_stats(features: dict[str, dict[str, Any]], advanced_stats: list[dict[str, Any]]) -> None:
    for entry in advanced_stats:
        team = entry["team"]
        if team not in features:
            continue

        offense = entry["offense"]
        defense = entry["defense"]
        row = features[team]

        row["offense_ppa"] = round(float(offense["ppa"]), 6)
        row["defense_ppa_allowed"] = round(float(defense["ppa"]), 6)
        row["offense_success_rate"] = round(float(offense["successRate"]), 6)
        row["defense_success_rate_allowed"] = round(float(defense["successRate"]), 6)
        row["offense_explosiveness"] = round(float(offense["explosiveness"]), 6)
        row["defense_explosiveness_allowed"] = round(float(defense["explosiveness"]), 6)
        row["offense_points_per_opportunity"] = round(float(offense["pointsPerOpportunity"]), 6)
        row["defense_points_per_opportunity_allowed"] = round(float(defense["pointsPerOpportunity"]), 6)
        row["offense_line_yards"] = round(float(offense["lineYards"]), 6)
        row["defense_line_yards_allowed"] = round(float(defense["lineYards"]), 6)
        row["offense_havoc_allowed"] = round(float(offense["havoc"]["total"]), 6)
        row["defense_havoc_created"] = round(float(defense["havoc"]["total"]), 6)
        row["offense_standard_down_success_rate"] = round(float(offense["standardDowns"]["successRate"]), 6)
        row["defense_standard_down_success_rate_allowed"] = round(float(defense["standardDowns"]["successRate"]), 6)
        row["offense_passing_down_success_rate"] = round(float(offense["passingDowns"]["successRate"]), 6)
        row["defense_passing_down_success_rate_allowed"] = round(float(defense["passingDowns"]["successRate"]), 6)


def apply_wepa(features: dict[str, dict[str, Any]], wepa_rows: list[dict[str, Any]]) -> None:
    for entry in wepa_rows:
        team = entry["team"]
        if team not in features:
            continue

        row = features[team]
        row["wepa_total"] = round(float(entry["epa"]["total"]), 6)
        row["wepa_pass"] = round(float(entry["epa"]["passing"]), 6)
        row["wepa_rush"] = round(float(entry["epa"]["rushing"]), 6)
        row["wepa_allowed_total"] = round(float(entry["epaAllowed"]["total"]), 6)
        row["wepa_success_rate"] = round(float(entry["successRate"]["total"]), 6)
        row["wepa_success_rate_allowed"] = round(float(entry["successRateAllowed"]["total"]), 6)
        row["wepa_explosiveness"] = round(float(entry["explosiveness"]), 6)
        row["wepa_explosiveness_allowed"] = round(float(entry["explosivenessAllowed"]), 6)
        row["wepa_rush_line_yards"] = round(float(entry["rushing"]["lineYards"]), 6)
        row["wepa_rush_line_yards_allowed"] = round(float(entry["rushingAllowed"]["lineYards"]), 6)


def apply_talent(features: dict[str, dict[str, Any]], talent_rows: list[dict[str, Any]]) -> None:
    for entry in talent_rows:
        team = entry["team"]
        if team not in features:
            continue
        features[team]["talent"] = round(float(entry["talent"]), 3)


def apply_polls(features: dict[str, dict[str, Any]], rankings: list[dict[str, Any]]) -> None:
    poll_positions = flatten_poll_positions(rankings)
    for team, values in poll_positions.items():
        if team not in features:
            continue
        features[team].update(values)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    base = args.input_root / str(args.year)

    games = load_json(base / "games.json")
    lines = load_json(base / "lines.json")
    advanced_stats = load_json(base / "advanced_team_stats.json")
    wepa_rows = load_json(base / "wepa.json")
    talent_rows = load_json(base / "talent.json")
    rankings = load_json(base / "rankings.json")

    line_lookup = summarize_lines(lines)
    features = build_game_features(games, line_lookup)
    apply_advanced_stats(features, advanced_stats)
    apply_wepa(features, wepa_rows)
    apply_talent(features, talent_rows)
    apply_polls(features, rankings)

    rows = sorted(
        (row for row in features.values() if row.get("classification") == "fbs"),
        key=lambda row: (row.get("conference", ""), row["team"]),
    )
    output_path = args.output_root / str(args.year) / "team_features.csv"
    write_csv(rows, output_path)
    print(f"Saved {len(rows)} team rows to {output_path}")


if __name__ == "__main__":
    main()

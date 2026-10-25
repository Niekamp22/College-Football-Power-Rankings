from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from cfb_weeks import display_week_for_game


RESUME_WEIGHT = 0.70
POWER_WEIGHT = 0.30
FBS_WIN_BASE = 1.0
QUALITY_WIN_BONUS = 2.0
FBS_LOSS_BASE = 5.0
BAD_LOSS_EXTRA = 2.0
FCS_WIN_CREDIT = 0.05
FCS_LOSS_PENALTY = 8.0
HEAD_TO_HEAD_WINDOW = 1.0
METHOD_VERSION = 1
DEFAULT_OUTPUT_ROOT = Path("output/polls")
GAME_COLUMNS = [
    "season", "game_id", "display_week", "season_type", "start_date", "team", "opponent",
    "site", "result", "score", "opponent_classification", "opponent_record",
    "opponent_power_rank", "opponent_strength", "win_credit", "loss_penalty", "resume_points",
]


def percentile_scores(values: pd.Series) -> pd.Series:
    """Equal inputs share a score; the common component scale is 0 to 100."""
    if len(values) <= 1 or values.nunique() <= 1:
        return pd.Series(50.0, index=values.index)
    return 100.0 * (values.rank(method="average") - 1.0) / (len(values) - 1.0)


def scale_scores(values: pd.Series) -> pd.Series:
    """Preserve score gaps while mapping each blend component onto 0 to 100."""
    span = values.max() - values.min()
    if len(values) <= 1 or span == 0:
        return pd.Series(50.0, index=values.index)
    return 100.0 * (values - values.min()) / span


def _head_to_head_order(
    teams: list[str], wins: Counter[tuple[str, str]],
) -> tuple[list[str], set[str]]:
    """Order close-score teams by direct results, keeping circular groups in score order."""
    order = {team: index for index, team in enumerate(teams)}
    edges = {team: [] for team in teams}
    for home_index, team in enumerate(teams):
        for opponent in teams[home_index + 1:]:
            difference = wins[team, opponent] - wins[opponent, team]
            if difference > 0:
                edges[team].append(opponent)
            elif difference < 0:
                edges[opponent].append(team)

    # Collapse cycles before sorting so three-way head-to-head cannot loop forever.
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    stacked: set[str] = set()
    components: list[list[str]] = []

    def visit(team: str) -> None:
        indices[team] = low[team] = len(indices)
        stack.append(team)
        stacked.add(team)
        for opponent in edges[team]:
            if opponent not in indices:
                visit(opponent)
                low[team] = min(low[team], low[opponent])
            elif opponent in stacked:
                low[team] = min(low[team], indices[opponent])
        if low[team] == indices[team]:
            group: list[str] = []
            while True:
                member = stack.pop()
                stacked.remove(member)
                group.append(member)
                if member == team:
                    break
            components.append(sorted(group, key=order.get))

    for team in teams:
        if team not in indices:
            visit(team)
    membership = {team: index for index, group in enumerate(components) for team in group}
    component_edges = {index: set() for index in range(len(components))}
    indegree = Counter()
    for team, opponents in edges.items():
        for opponent in opponents:
            source, target = membership[team], membership[opponent]
            if source != target and target not in component_edges[source]:
                component_edges[source].add(target)
                indegree[target] += 1
    ready = [index for index in component_edges if indegree[index] == 0]
    result: list[str] = []
    while ready:
        selected = min(ready, key=lambda index: min(order[team] for team in components[index]))
        ready.remove(selected)
        result.extend(components[selected])
        for target in component_edges[selected]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    circular = {team for group in components if len(group) > 1 for team in group}
    return result, circular


def apply_head_to_head(poll: pd.DataFrame, wins: Counter[tuple[str, str]]) -> pd.DataFrame:
    ordered = poll.sort_values(["poll_score", "resume_raw", "power_rating", "team"],
                               ascending=[False, False, False, True]).copy()
    ordered["score_rank"] = range(1, len(ordered) + 1)
    positions: list[str] = []
    circular_teams: set[str] = set()
    band_members: dict[str, list[str]] = {}
    start = 0
    while start < len(ordered):
        anchor = float(ordered.iloc[start]["poll_score"])
        end = start + 1
        while end < len(ordered) and anchor - float(ordered.iloc[end]["poll_score"]) <= HEAD_TO_HEAD_WINDOW + 1e-9:
            end += 1
        group, circular = _head_to_head_order(ordered.iloc[start:end]["team"].tolist(), wins)
        for team in group:
            band_members[team] = group
        positions.extend(group)
        circular_teams.update(circular)
        start = end
    ordered = ordered.set_index("team").loc[positions].reset_index()
    ordered["rank"] = range(1, len(ordered) + 1)
    ordered["head_to_head_adjustment"] = ordered["score_rank"] - ordered["rank"]
    notes = []
    for row in ordered.itertuples():
        if row.team in circular_teams:
            notes.append("Circular head-to-head; score order retained")
        elif row.head_to_head_adjustment != 0:
            direct_wins = [opponent for opponent in band_members[row.team]
                           if wins[row.team, opponent] > wins[opponent, row.team]
                           and abs(float(ordered.loc[ordered.team == opponent, "poll_score"].iloc[0]) - row.poll_score) <= HEAD_TO_HEAD_WINDOW + 1e-9]
            direct_losses = [opponent for opponent in band_members[row.team]
                             if wins[opponent, row.team] > wins[row.team, opponent]
                             and abs(float(ordered.loc[ordered.team == opponent, "poll_score"].iloc[0]) - row.poll_score) <= HEAD_TO_HEAD_WINDOW + 1e-9]
            facts = (["Beat " + ", ".join(direct_wins)] if direct_wins else [])
            facts += (["Lost to " + ", ".join(direct_losses)] if direct_losses else [])
            notes.append("Close-score head-to-head: " + "; ".join(facts) if facts else "Close-score head-to-head ordering")
        else:
            notes.append("")
    ordered["head_to_head_note"] = notes
    return ordered


def build_poll(
    ratings: pd.DataFrame, games: list[dict], season: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if ratings.empty or not {"team", "rating", "conference"}.issubset(ratings.columns):
        raise ValueError("Josh's Poll requires team, conference, and rating columns.")
    if ratings["team"].duplicated().any():
        raise ValueError("Duplicate teams in the power ratings.")
    poll = ratings[["team", "conference", "rating"]].rename(columns={"rating": "power_rating"}).copy()
    poll["power_rating"] = pd.to_numeric(poll["power_rating"], errors="raise")
    if poll["power_rating"].isna().any() or not poll["power_rating"].map(lambda x: float("-inf") < x < float("inf")).all():
        raise ValueError("Missing or non-finite power ratings.")
    poll["power_rank"] = poll["power_rating"].rank(ascending=False, method="min").astype(int)
    strength = (percentile_scores(poll["power_rating"]) / 100.0).set_axis(poll["team"]).to_dict()
    lookup = poll.set_index("team").to_dict("index")
    teams = set(lookup)
    records: dict[str, Counter] = defaultdict(Counter)
    record_ids: set[object] = set()
    for game in games:
        if int(game.get("season") or 0) != season or not game.get("completed"):
            continue
        if game.get("homePoints") is None or game.get("awayPoints") is None or game.get("id") in record_ids:
            continue
        record_ids.add(game.get("id"))
        if game["homePoints"] != game["awayPoints"]:
            winner, loser = ((game["homeTeam"], game["awayTeam"]) if game["homePoints"] > game["awayPoints"]
                             else (game["awayTeam"], game["homeTeam"]))
            records[winner]["wins"] += 1
            records[loser]["losses"] += 1
    completed: list[dict] = []
    seen: set[object] = set()
    for game in games:
        if int(game.get("season") or 0) != season or not game.get("completed"):
            continue
        home, away = game["homeTeam"], game["awayTeam"]
        if home not in teams and away not in teams:
            continue
        game_id = game.get("id")
        if game_id is None or game_id in seen:
            raise ValueError("Missing or duplicate completed game ID in Josh's Poll inputs.")
        seen.add(game_id)
        if game.get("homePoints") is None or game.get("awayPoints") is None:
            raise ValueError(f"Completed game {game_id} is missing its final score.")
        if game["homePoints"] == game["awayPoints"]:
            raise ValueError(f"Completed game {game_id} has no decided winner.")
        for side in ("home", "away"):
            if game.get(f"{side}Classification") == "fbs" and game[f"{side}Team"] not in teams:
                raise ValueError(f"Missing current power rating for {game[f'{side}Team']}.")
        completed.append(game)
    completed.sort(key=lambda game: (game.get("startDate") or "", str(game["id"])))
    wins: Counter[tuple[str, str]] = Counter()
    rows: list[dict] = []
    for game in completed:
        for side, other in (("home", "away"), ("away", "home")):
            team, opponent = game[f"{side}Team"], game[f"{other}Team"]
            if team not in teams:
                continue
            is_fbs = opponent in teams
            classification = game.get(f"{other}Classification")
            if not is_fbs and classification != "fcs":
                raise ValueError(f"Unsupported or unknown opponent classification for {opponent}: {classification}.")
            won = game[f"{side}Points"] > game[f"{other}Points"]
            quality = strength[opponent] if is_fbs else 0.0
            credit = (FBS_WIN_BASE + QUALITY_WIN_BONUS * quality**3 if is_fbs else FCS_WIN_CREDIT) if won else 0.0
            penalty = (FBS_LOSS_BASE + BAD_LOSS_EXTRA * (1.0 - quality)**2 if is_fbs else FCS_LOSS_PENALTY) if not won else 0.0
            if won and is_fbs:
                wins[team, opponent] += 1
            rows.append({
                "season": season, "game_id": game["id"], "display_week": display_week_for_game(game),
                "season_type": game.get("seasonType", "regular"), "start_date": game.get("startDate", ""),
                "team": team, "opponent": opponent,
                "site": "Neutral" if game.get("neutralSite") else "Home" if side == "home" else "Away",
                "result": "W" if won else "L", "score": f"{game[f'{side}Points']}-{game[f'{other}Points']}",
                "opponent_classification": "fbs" if is_fbs else "fcs",
                "opponent_record": f"{records[opponent]['wins']}-{records[opponent]['losses']}",
                "opponent_power_rank": lookup[opponent]["power_rank"] if is_fbs else None,
                "opponent_strength": quality, "win_credit": credit, "loss_penalty": penalty,
                "resume_points": credit - penalty,
            })
    detail = pd.DataFrame(rows, columns=GAME_COLUMNS)
    through_week = int(detail["display_week"].max()) if not detail.empty else -1
    summaries = []
    for team in poll["team"]:
        games_for_team = detail[detail["team"].eq(team)]
        victories = games_for_team[games_for_team["result"].eq("W")]
        defeats = games_for_team[games_for_team["result"].eq("L")]
        fbs = games_for_team[games_for_team["opponent_classification"].eq("fbs")]
        best = victories.sort_values(["win_credit", "opponent"], ascending=[False, True])
        worst = defeats.sort_values(["loss_penalty", "opponent"], ascending=[False, True])
        summaries.append({
            "team": team, "season": season, "through_week": through_week, "games_played": len(games_for_team),
            "wins": len(victories), "losses": len(defeats), "record": f"{len(victories)}-{len(defeats)}",
            "fbs_wins": int((fbs["result"] == "W").sum()), "fbs_losses": int((fbs["result"] == "L").sum()),
            "fcs_wins": int((victories["opponent_classification"] == "fcs").sum()),
            "win_credits": float(games_for_team["win_credit"].sum()),
            "loss_penalties": float(games_for_team["loss_penalty"].sum()),
            "resume_raw": float(games_for_team["resume_points"].sum()),
            "top_25_wins": int((victories["opponent_power_rank"] <= 25).sum()),
            "top_50_wins": int((victories["opponent_power_rank"] <= 50).sum()),
            "schedule_strength": float(games_for_team["opponent_strength"].mean() * 100.0) if len(games_for_team) else None,
            "best_win": str(best.iloc[0]["opponent"]) if not best.empty else "None",
            "worst_loss": str(worst.iloc[0]["opponent"]) if not worst.empty else "None",
        })
    poll = poll.merge(pd.DataFrame(summaries), on="team", validate="one_to_one")
    poll["power_score"] = scale_scores(poll["power_rating"])
    played = poll["games_played"] > 0
    poll["resume_score"] = float("nan")
    poll.loc[played, "resume_score"] = scale_scores(poll.loc[played, "resume_raw"])
    poll["resume_rank"] = poll["resume_raw"].where(played).rank(method="min", ascending=False).astype("Int64")
    poll["resume_contribution"] = RESUME_WEIGHT * poll["resume_score"]
    poll["power_contribution"] = POWER_WEIGHT * poll["power_score"]
    poll["poll_score"] = poll["resume_contribution"] + poll["power_contribution"]
    ranked = apply_head_to_head(poll.loc[played], wins)
    unranked = poll.loc[~played].copy()
    unranked["head_to_head_note"] = "No completed games"
    result = pd.concat([ranked, unranked], ignore_index=True)
    for column in ("rank", "score_rank", "head_to_head_adjustment"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    result["previous_rank"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["movement"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    return result, detail


def generate_poll(season: int, ratings_path: Path, games_path: Path, output_root: Path = DEFAULT_OUTPUT_ROOT) -> pd.DataFrame:
    ratings = pd.read_csv(ratings_path)
    games = json.loads(games_path.read_text(encoding="utf-8"))
    poll, detail = build_poll(ratings, games, season)
    season_root = output_root / str(season)
    season_root.mkdir(parents=True, exist_ok=True)
    through_week = int(poll["through_week"].iloc[0])
    older = sorted(path for path in season_root.glob("week_*_poll.csv")
                   if int(path.stem.split("_")[1]) < through_week)
    if older:
        previous = pd.read_csv(older[-1]).set_index("team")["rank"]
        poll["previous_rank"] = poll["team"].map(previous).astype("Int64")
        poll["movement"] = (poll["previous_rank"] - poll["rank"]).astype("Int64")
    metadata = {
        "season": season, "through_week": through_week, "method_version": METHOD_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "teams": len(poll), "ranked_teams": int(poll["rank"].notna().sum()), "team_game_rows": len(detail),
        "ratings_sha256": hashlib.sha256(ratings_path.read_bytes()).hexdigest(),
        "games_sha256": hashlib.sha256(games_path.read_bytes()).hexdigest(),
        "resume_weight": RESUME_WEIGHT, "power_weight": POWER_WEIGHT,
        "fbs_win_base": FBS_WIN_BASE, "quality_win_bonus": QUALITY_WIN_BONUS,
        "fbs_loss_base": FBS_LOSS_BASE, "bad_loss_extra": BAD_LOSS_EXTRA,
        "fcs_win_credit": FCS_WIN_CREDIT, "fcs_loss_penalty": FCS_LOSS_PENALTY,
        "head_to_head_window": HEAD_TO_HEAD_WINDOW,
    }
    poll.to_csv(output_root / f"joshs_poll_{season}.csv", index=False, float_format="%.6f")
    detail.to_csv(output_root / f"joshs_poll_games_{season}.csv", index=False, float_format="%.6f")
    (season_root / "latest_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if through_week >= 0:
        # An edition stays live during its week. Earlier-week editions remain untouched.
        poll.to_csv(season_root / f"week_{through_week:02d}_poll.csv", index=False, float_format="%.6f")
        detail.to_csv(season_root / f"week_{through_week:02d}_games.csv", index=False, float_format="%.6f")
        (season_root / f"week_{through_week:02d}_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved Josh's Poll for {season}, through Week {through_week}, with {metadata['ranked_teams']} ranked teams.")
    return poll


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Josh's Poll: 70% resume, 30% power.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--ratings", type=Path, default=Path("output/cfbd_power_ratings_current.csv"))
    parser.add_argument("--games", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    generate_poll(args.season, args.ratings, args.games or Path(f"data/cfbd/raw/{args.season}/games.json"), args.output_root)


if __name__ == "__main__":
    main()

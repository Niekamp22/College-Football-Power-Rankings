from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from joshs_poll import apply_head_to_head, build_poll, generate_poll


def ratings() -> pd.DataFrame:
    return pd.DataFrame([
        {"team": "Elite", "conference": "Test", "rating": 25.0},
        {"team": "Alpha", "conference": "Test", "rating": 15.0},
        {"team": "Beta", "conference": "Test", "rating": 14.0},
        {"team": "Weak", "conference": "Test", "rating": -20.0},
    ])


def game(game_id: int, home: str, away: str, home_points: int, away_points: int, week: int = 3, **extra) -> dict:
    return {
        "id": game_id, "season": 2026, "seasonType": "regular", "week": week,
        "startDate": f"2026-09-{12 + week:02d}T16:00:00Z", "completed": True,
        "homeTeam": home, "awayTeam": away, "homeClassification": "fbs", "awayClassification": "fbs",
        "homePoints": home_points, "awayPoints": away_points, "neutralSite": False, **extra,
    }


class JoshsPollTests(unittest.TestCase):
    def test_winning_margin_does_not_change_poll(self) -> None:
        games = [game(1, "Alpha", "Beta", 21, 20), game(2, "Elite", "Weak", 14, 7)]
        first, _ = build_poll(ratings(), games, 2026)
        games[0]["homePoints"] = 70
        second, _ = build_poll(ratings(), games, 2026)
        pd.testing.assert_frame_equal(first, second)

    def test_fcs_credit_loss_penalty_and_actual_record(self) -> None:
        games = [
            game(1, "Alpha", "FCS", 21, 20, awayClassification="fcs"),
            game(2, "Alpha", "FCS", 7, 14, awayClassification="fcs"),
        ]
        poll, detail = build_poll(ratings(), games, 2026)
        alpha = poll.set_index("team").loc["Alpha"]
        self.assertEqual(alpha.record, "1-1")
        self.assertAlmostEqual(alpha.win_credits, 0.05)
        self.assertAlmostEqual(alpha.loss_penalties, 8.0)
        self.assertAlmostEqual(detail.resume_points.sum(), -7.95)
        self.assertTrue(poll.set_index("team").loc["Elite", "head_to_head_note"] == "No completed games")
        self.assertTrue(pd.isna(poll.set_index("team").loc["Elite", "rank"]))

    def test_opponents_are_reassessed_using_current_power(self) -> None:
        games = [game(1, "Alpha", "Beta", 21, 20)]
        _, old = build_poll(ratings(), games, 2026)
        stronger = ratings()
        stronger.loc[stronger.team == "Beta", "rating"] = 40.0
        _, current = build_poll(stronger, games, 2026)
        self.assertGreater(current.loc[current.team == "Alpha", "win_credit"].iloc[0],
                           old.loc[old.team == "Alpha", "win_credit"].iloc[0])

    def test_losses_matter_but_a_large_quality_gap_can_overcome_one(self) -> None:
        # Five ordinary wins versus four wins over the strongest opponent plus one loss.
        unbeaten = [game(index, "Alpha", "Weak", 14, 7) for index in range(1, 6)]
        ordinary = [game(index, "Beta", "Weak", 14, 7) for index in range(6, 10)]
        loss = game(10, "Elite", "Beta", 14, 7)
        modest, _ = build_poll(ratings(), unbeaten + ordinary + [loss], 2026)
        modest = modest.set_index("team")
        self.assertGreater(modest.loc["Alpha", "resume_raw"], modest.loc["Beta", "resume_raw"])
        strong = [game(index, "Beta", "Elite", 14, 7) for index in range(6, 10)]
        disparity, _ = build_poll(ratings(), unbeaten + strong + [loss], 2026)
        disparity = disparity.set_index("team")
        self.assertGreater(disparity.loc["Beta", "resume_raw"], disparity.loc["Alpha", "resume_raw"])

    def test_incomplete_and_other_season_games_do_not_count_and_blend_reconciles(self) -> None:
        games = [game(1, "Alpha", "Beta", 21, 20),
                 game(2, "Elite", "Weak", 14, 7, completed=False),
                 game(3, "Elite", "Weak", 14, 7, season=2025)]
        poll, detail = build_poll(ratings(), games, 2026)
        self.assertEqual(len(detail), 2)
        for row in poll[poll["games_played"] > 0].itertuples():
            self.assertAlmostEqual(row.poll_score, 0.7 * row.resume_score + 0.3 * row.power_score)

    def test_head_to_head_only_reorders_close_scores_and_handles_cycles(self) -> None:
        board = pd.DataFrame([
            {"team": "Alpha", "poll_score": 95.0, "resume_raw": 10.0, "power_rating": 10.0},
            {"team": "Beta", "poll_score": 94.5, "resume_raw": 9.0, "power_rating": 9.0},
            {"team": "Elite", "poll_score": 90.0, "resume_raw": 8.0, "power_rating": 8.0},
        ])
        wins = Counter({("Beta", "Alpha"): 1, ("Elite", "Alpha"): 1})
        ordered = apply_head_to_head(board, wins)
        self.assertEqual(ordered.team.tolist(), ["Beta", "Alpha", "Elite"])
        board["poll_score"] = [95.0, 94.8, 94.5]
        cycle = Counter({("Alpha", "Beta"): 1, ("Beta", "Elite"): 1, ("Elite", "Alpha"): 1})
        ordered = apply_head_to_head(board, cycle)
        self.assertEqual(ordered.team.tolist(), ["Alpha", "Beta", "Elite"])
        self.assertTrue(ordered.head_to_head_note.str.contains("Circular").all())

    def test_head_to_head_band_does_not_chain_beyond_one_point(self) -> None:
        board = pd.DataFrame([
            {"team": name, "poll_score": score, "resume_raw": score, "power_rating": score}
            for name, score in [("Alpha", 95.0), ("Beta", 94.4), ("Elite", 93.8)]
        ])
        ordered = apply_head_to_head(board, Counter({("Elite", "Beta"): 1, ("Beta", "Alpha"): 1}))
        self.assertEqual(ordered.team.tolist(), ["Beta", "Alpha", "Elite"])

    def test_duplicate_games_and_missing_fbs_opponent_ratings_fail(self) -> None:
        final = game(1, "Alpha", "Beta", 14, 7)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_poll(ratings(), [final, final], 2026)
        with self.assertRaisesRegex(ValueError, "Missing current power"):
            build_poll(ratings(), [game(2, "Alpha", "Unknown", 14, 7)], 2026)

    def test_weekly_history_and_movement_use_a_previous_week(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ratings_path, games_path = root / "ratings.csv", root / "games.json"
            ratings().to_csv(ratings_path, index=False)
            games = [game(1, "Alpha", "Beta", 14, 7, week=3)]
            games_path.write_text(json.dumps(games), encoding="utf-8")
            first = generate_poll(2026, ratings_path, games_path, root / "polls")
            archived = root / "polls/2026/week_03_poll.csv"
            original = archived.read_bytes()
            self.assertTrue(first.previous_rank.isna().all())
            games.append(game(2, "Beta", "Elite", 21, 7, week=4))
            games_path.write_text(json.dumps(games), encoding="utf-8")
            second = generate_poll(2026, ratings_path, games_path, root / "polls")
            self.assertEqual(archived.read_bytes(), original)
            self.assertFalse(second.previous_rank.dropna().empty)
            repeated = generate_poll(2026, ratings_path, games_path, root / "polls")
            pd.testing.assert_series_equal(second.previous_rank, repeated.previous_rank)


if __name__ == "__main__":
    unittest.main()

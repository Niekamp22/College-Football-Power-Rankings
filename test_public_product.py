from __future__ import annotations

import unittest

import pandas as pd

from app import default_week_index, format_percent, is_frozen_rating_source, summarize_completed_games
from project_win_totals import build_projections


def sample_ratings() -> list[dict[str, object]]:
    return [
        {"team": "Alpha", "conference": "Test", "rating": 10.0},
        {"team": "Beta", "conference": "Test", "rating": 0.0},
        {"team": "Gamma", "conference": "Test", "rating": -4.0},
    ]


class PublicProductTest(unittest.TestCase):
    def test_in_season_projection_counts_actual_results_then_future_expectation(self) -> None:
        games = [
        {
            "id": 1,
            "season": 2026,
            "seasonType": "regular",
            "week": 1,
            "startDate": "2026-09-05T16:00:00Z",
            "homeTeam": "Alpha",
            "awayTeam": "Beta",
            "homeClassification": "fbs",
            "awayClassification": "fbs",
            "neutralSite": False,
            "completed": True,
            "homePoints": 7,
            "awayPoints": 14,
        },
        {
            "id": 2,
            "season": 2026,
            "seasonType": "regular",
            "week": 2,
            "startDate": "2026-09-12T16:00:00Z",
            "homeTeam": "Alpha",
            "awayTeam": "Gamma",
            "homeClassification": "fbs",
            "awayClassification": "fbs",
            "neutralSite": False,
            "completed": False,
            "homePoints": None,
            "awayPoints": None,
        },
        ]

        summary, projected_games = build_projections(sample_ratings(), games, 2026)
        alpha = next(row for row in summary if row["team"] == "Alpha")

        self.assertEqual(alpha["actual_wins"], 0.0)
        self.assertEqual(alpha["actual_losses"], 1.0)
        self.assertEqual(alpha["remaining_games"], 1)
        self.assertEqual(alpha["projected_wins"], alpha["remaining_expected_wins"])
        self.assertEqual({row["status"] for row in projected_games}, {"Final", "Upcoming"})

    def test_neutral_game_rows_share_one_game_id_for_ui_deduplication(self) -> None:
        games = [
        {
            "id": 99,
            "season": 2026,
            "seasonType": "regular",
            "week": 3,
            "startDate": "2026-09-19T23:00:00Z",
            "homeTeam": "Alpha",
            "awayTeam": "Beta",
            "homeClassification": "fbs",
            "awayClassification": "fbs",
            "neutralSite": True,
            "completed": False,
        }
        ]

        _, rows = build_projections(sample_ratings(), games, 2026)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["game_id"] for row in rows}, {99})
        self.assertEqual(len(pd.DataFrame(rows).drop_duplicates("game_id")), 1)

    def test_default_week_is_first_future_week(self) -> None:
        board = pd.DataFrame(
            {
            "display_week": [0, 1, 2, 3],
            "start_date": [
                "2026-08-29T16:00:00Z",
                "2026-09-05T16:00:00Z",
                "2026-09-12T16:00:00Z",
                "2026-09-26T16:00:00Z",
            ],
            "status": ["Final", "Final", "Final", "Upcoming"],
            }
        )

        self.assertEqual(default_week_index(board, pd.Timestamp("2026-09-21T12:00:00Z")), 3)

    def test_public_helpers_make_provenance_and_percentages_clear(self) -> None:
        self.assertEqual(format_percent(0.8839), "88.4%")
        self.assertTrue(is_frozen_rating_source("week_04_snapshot"))
        self.assertFalse(is_frozen_rating_source("current_retrospective"))

        games = pd.DataFrame(
            {
            "display_week": [4],
            "absolute_model_error": [7.0],
            "absolute_market_error": [9.0],
            "winner_model_result": ["correct"],
            "winner_market_result": ["wrong"],
            "edge_result": ["right_side"],
            }
        )
        summary = summarize_completed_games(games).iloc[0]
        self.assertEqual(summary["model_margin_mae"], 7.0)
        self.assertEqual(summary["model_winner_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()

import unittest

from dual_ratings import build_dual_ratings
from snapshot_rankings import next_prediction_week


class DualRatingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"team": "Alpha", "latest_team_postgame_elo": 1600, "talent": 800},
            {"team": "Beta", "latest_team_postgame_elo": 1500, "talent": 700},
            {"team": "Gamma", "latest_team_postgame_elo": 1400, "talent": 600},
        ]
        self.games = [
            {
                "homeTeam": "Alpha",
                "awayTeam": "Beta",
                "homeClassification": "fbs",
                "awayClassification": "fbs",
                "completed": True,
                "homePoints": 35,
                "awayPoints": 14,
            },
            {
                "homeTeam": "Beta",
                "awayTeam": "Gamma",
                "homeClassification": "fbs",
                "awayClassification": "fbs",
                "completed": True,
                "homePoints": 28,
                "awayPoints": 21,
            },
        ]
        self.lines = [
            {
                "homeTeam": "Alpha",
                "awayTeam": "Beta",
                "homeClassification": "fbs",
                "awayClassification": "fbs",
                "lines": [{"spread": -14}],
            },
            {
                "homeTeam": "Beta",
                "awayTeam": "Gamma",
                "homeClassification": "fbs",
                "awayClassification": "fbs",
                "lines": [{"spread": -7}],
            },
        ]

    def test_components_are_centered_and_blended(self) -> None:
        components, diagnostics = build_dual_ratings(self.rows, self.games, self.lines)
        self.assertAlmostEqual(sum(row["rating"] for row in components.values()), 0.0)
        self.assertGreater(components["Alpha"]["rating"], components["Beta"]["rating"])
        self.assertGreater(components["Beta"]["rating"], components["Gamma"]["rating"])
        self.assertAlmostEqual(
            components["Alpha"]["rating"],
            (0.6 * components["Alpha"]["football_rating"]) + (0.4 * components["Alpha"]["market_rating"]),
        )
        self.assertEqual(diagnostics["rating_system"], "dual")

    def test_snapshot_week_follows_latest_completed_week(self) -> None:
        games = [
            {
                "season": 2026,
                "seasonType": "regular",
                "week": 3,
                "completed": True,
                "homeClassification": "fbs",
                "awayClassification": "fbs",
                "startDate": "2026-09-19T12:00:00Z",
            }
        ]
        self.assertEqual(next_prediction_week(games, 2026), 4)


if __name__ == "__main__":
    unittest.main()

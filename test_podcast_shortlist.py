import unittest

import pandas as pd

from app import build_podcast_shortlist


class PodcastShortlistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ratings = pd.DataFrame(
            [
                {
                    "team": "Home",
                    "football_rating": 10.0,
                    "market_rating": 9.0,
                    "market_gap": -1.0,
                    "rating_confidence": "High",
                },
                {
                    "team": "Away",
                    "football_rating": 4.0,
                    "market_rating": 4.0,
                    "market_gap": 0.0,
                    "rating_confidence": "Medium",
                },
            ]
        )

    def test_only_well_supported_fbs_candidates_survive(self) -> None:
        common = {
            "display_week": 4,
            "commence_time": "2026-09-26T16:00:00Z",
            "home_team": "Home",
            "away_team": "Away",
            "neutral_site": False,
            "book_count": 8,
            "model_home_spread": -8.5,
            "market_home_margin": 3.0,
            "edge_home_points": 5.5,
            "absolute_edge_points": 5.5,
            "edge_side": "Home",
            "selected_best_spread": -2.5,
            "selected_best_price": -105,
            "selected_best_book": "book",
            "line_shopping_value": 0.5,
            "betting_status": "Standard",
        }
        odds = pd.DataFrame(
            [
                {**common, "game_type": "FBS vs FBS"},
                {**common, "game_type": "FCS involved", "away_team": "FCS Team"},
            ]
        )

        shortlist = build_podcast_shortlist(odds, self.ratings)

        self.assertEqual(len(shortlist), 1)
        self.assertEqual(shortlist.iloc[0]["Model Lean"], "Home")
        self.assertEqual(shortlist.iloc[0]["Model Fair Line"], -8.5)


if __name__ == "__main__":
    unittest.main()

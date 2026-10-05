import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from best_bets import LEDGER_COLUMNS, grade_ledger, payout_units


class BestBetTrackerTest(unittest.TestCase):
    def test_american_odds_payout(self) -> None:
        self.assertAlmostEqual(payout_units(-110), 0.9091, places=4)
        self.assertEqual(payout_units(125), 1.25)

    def test_completed_pick_is_graded_with_clv(self) -> None:
        ledger = pd.DataFrame(
            [
                {
                    "season": 2026,
                    "display_week": 6,
                    "week_label": "Week 6",
                    "selection_rank": 1,
                    "event_id": "event-1",
                    "captured_at_utc": "2026-10-05T12:00:00+00:00",
                    "kickoff_utc": "2026-10-10T16:00:00Z",
                    "matchup": "Away at Home",
                    "away_team": "Away",
                    "home_team": "Home",
                    "pick_team": "Home",
                    "opponent": "Away",
                    "locked_spread": -3.0,
                    "locked_price": -110,
                    "locked_book": "book",
                    "model_fair_line": -7.0,
                    "model_edge": 4.0,
                    "candidate_score": 90.0,
                    "book_count": 8,
                    "line_shopping_gain": 0.5,
                    "reasoning": "Test reasoning",
                    "status": "pending",
                    "units": 0.0,
                }
            ]
        ).reindex(columns=LEDGER_COLUMNS)

        schedule_path = MagicMock(spec=Path)
        schedule_path.exists.return_value = True
        schedule_path.read_text.return_value = json.dumps(
            [
                {
                    "homeTeam": "Home",
                    "awayTeam": "Away",
                    "completed": True,
                    "homePoints": 27,
                    "awayPoints": 20,
                }
            ]
        )
        clv = pd.DataFrame(
            [
                {
                    "event_id": "event-1",
                    "edge_side": "Home",
                    "closing_side_spread": -4.0,
                }
            ]
        )
        with patch("best_bets.load_frame", return_value=clv):
            graded = grade_ledger(ledger, schedule_path, Path("clv.csv"))

        pick = graded.iloc[0]
        self.assertEqual(pick["ats_result"], "win")
        self.assertEqual(pick["cover_margin"], 4.0)
        self.assertEqual(pick["clv_points"], 1.0)
        self.assertAlmostEqual(pick["units"], 0.909, places=3)


if __name__ == "__main__":
    unittest.main()

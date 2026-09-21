import unittest

from matchup_adjustments import betting_status, matchup_margin_std_dev


class MatchupAdjustmentsTest(unittest.TestCase):
    def test_fcs_games_use_wider_uncertainty(self) -> None:
        self.assertEqual(matchup_margin_std_dev("fbs", "fcs"), 20.0)
        self.assertEqual(matchup_margin_std_dev("fbs", "fbs"), 16.0)

    def test_fcs_betting_statuses(self) -> None:
        self.assertEqual(betting_status("FCS involved", 8.0, -10.0), "Qualified FCS favorite")
        self.assertEqual(betting_status("FCS involved", -8.0, -10.0), "Pass - FCS underdog")
        self.assertEqual(betting_status("FCS involved", 16.0, -10.0), "Pass - FCS extreme edge")
        self.assertEqual(betting_status("FCS involved", 4.0, -10.0), "Pass - FCS low edge")

    def test_non_fcs_extreme_edge_is_reviewed(self) -> None:
        self.assertEqual(betting_status("FBS vs FBS", 16.0, -3.0), "Review - extreme edge")


if __name__ == "__main__":
    unittest.main()

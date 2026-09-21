import unittest

from sync_odds_api import best_spread_offer, break_even_probability


class OddsTrackingTest(unittest.TestCase):
    def test_best_spread_is_selected_before_price(self) -> None:
        offer = best_spread_offer([(3.0, -105, "book_a"), (3.5, -120, "book_b")])
        self.assertEqual(offer, (3.5, -120, "book_b"))

    def test_price_breaks_ties_between_equal_spreads(self) -> None:
        offer = best_spread_offer([(3.0, -110, "book_a"), (3.0, -105, "book_b")])
        self.assertEqual(offer, (3.0, -105, "book_b"))

    def test_american_price_break_even_probability(self) -> None:
        self.assertAlmostEqual(break_even_probability(-110), 0.5238095)
        self.assertAlmostEqual(break_even_probability(120), 100 / 220)


if __name__ == "__main__":
    unittest.main()

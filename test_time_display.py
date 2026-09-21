import unittest

from app import format_eastern_time


class EasternTimeDisplayTest(unittest.TestCase):
    def test_daylight_time_is_converted_to_eastern(self) -> None:
        self.assertEqual(format_eastern_time("2026-09-26T16:00:00Z"), "Sat Sep 26, 12:00 PM ET")

    def test_standard_time_is_converted_to_eastern(self) -> None:
        self.assertEqual(format_eastern_time("2026-12-05T16:00:00Z"), "Sat Dec 5, 11:00 AM ET")

    def test_missing_time_is_tbd(self) -> None:
        self.assertEqual(format_eastern_time(""), "TBD")


if __name__ == "__main__":
    unittest.main()

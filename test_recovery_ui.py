from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from streamlit.testing.v1 import AppTest

from recovery_ui import PAGES, read_csv


APP_PATH = Path(__file__).with_name("app.py")


class RecoveryViewTests(unittest.TestCase):
    def test_page_navigation_reads_only_its_own_csv_sources(self) -> None:
        expected = {
            "rankings": ["cfbd_power_ratings_current.csv"],
            "weekly": ["projections/projected_games_2026.csv"],
            "forecast": ["projections/projected_win_totals_2026.csv"],
        }
        for page, paths in expected.items():
            with self.subTest(page=page):
                app = AppTest.from_file(str(APP_PATH))
                app.query_params["page"] = page
                with patch("recovery_ui.read_csv", wraps=read_csv) as reader:
                    app.run(timeout=60)
                self.assertFalse(app.exception)
                self.assertEqual([call.args[0] for call in reader.call_args_list], paths)

    def test_default_view_avoids_failing_widget_modules(self) -> None:
        app = AppTest.from_file(str(APP_PATH)).run(timeout=60)
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertFalse(app.selectbox)
        self.assertFalse(app.text_input)
        self.assertFalse(app.checkbox)
        self.assertFalse(app.dataframe)
        self.assertFalse(app.metric)
        source = "\n".join(element.value for element in app.markdown)
        self.assertIn('<form class="recovery-form"', source)
        self.assertIn("<table", source)
        self.assertIn("Recovery view", source)

    def test_all_recovery_pages_render(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        for page in PAGES:
            with self.subTest(page=page):
                app.query_params.clear()
                app.query_params["page"] = page
                app.run(timeout=60)
                self.assertFalse(app.exception, [error.message for error in app.exception])
                self.assertFalse(app.dataframe)
                self.assertFalse(app.selectbox)

    def test_poll_filters_and_resume_still_work(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        app.query_params.update({"page": "poll", "scope": "All FBS teams", "search": "UCLA", "team": "UCLA"})
        app.run(timeout=60)
        self.assertFalse(app.exception)
        source = "\n".join(element.value for element in app.markdown)
        self.assertIn("80% resume + 20% power", source)
        self.assertIn("<h3>UCLA:", source)
        self.assertIn("Opponent Power Rank", source)
        self.assertIn("Win Credits", source)

    def test_invalid_edge_range_is_rejected_and_form_values_are_escaped(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        app.query_params.update({"page": "odds", "min_edge": "10", "max_edge": "3", "search": '<script>alert("x")</script>'})
        fixture = pd.DataFrame([{"market_status": "open_market", "display_week": 10}])
        with patch("recovery_ui.read_csv", side_effect=lambda relative: fixture if relative.startswith("odds/") else read_csv(relative)):
            app.run(timeout=60)
        self.assertFalse(app.exception)
        source = "\n".join(element.value for element in app.markdown)
        self.assertIn("Choose an edge range between 0 and 50", source)
        self.assertNotIn('<script>alert("x")</script>', source)
        self.assertIn("&lt;script&gt;", source)


if __name__ == "__main__":
    unittest.main()

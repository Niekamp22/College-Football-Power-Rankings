from __future__ import annotations

import unittest
import re
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from streamlit.testing.v1 import AppTest

from recovery_ui import PAGES, _HTML_PARTS, _PAGE_PARAMS, entry, read_csv, show_odds, show_rankings, show_weekly


APP_PATH = Path(__file__).with_name("app.py")


class RecoveryViewTests(unittest.TestCase):
    def render_filtered(self, renderer, params, *args):
        parts = []
        html_token = _HTML_PARTS.set(parts)
        params_token = _PAGE_PARAMS.set(params)
        try:
            renderer(*args)
        finally:
            _PAGE_PARAMS.reset(params_token)
            _HTML_PARTS.reset(html_token)
        return "".join(parts)

    def test_entry_is_editable_without_a_controlled_value(self) -> None:
        token = _PAGE_PARAMS.set({"search": "Texas & A&M", "min_edge": "2.5"})
        try:
            for name, numeric in [("search", False), ("min_edge", True)]:
                source = entry(name, name, numeric=numeric)
                self.assertIn('<textarea rows="1"', source)
                self.assertNotIn(" value=", source)
                self.assertNotIn("readonly", source.lower())
                self.assertNotIn("disabled", source.lower())
            self.assertIn("Texas &amp; A&amp;M</textarea>", entry("search", "Find a team"))
            self.assertIn('inputmode="decimal"', entry("min_edge", "Minimum edge", numeric=True))
        finally:
            _PAGE_PARAMS.reset(token)

    def test_rankings_search_and_conference_filters(self) -> None:
        ratings = pd.DataFrame([
            {"team": "Texas", "conference": "SEC", "rating": 20},
            {"team": "Texas Tech", "conference": "Big 12", "rating": 15},
            {"team": "Ohio State", "conference": "Big Ten", "rating": 25},
        ])
        source = self.render_filtered(show_rankings, {
            "search": " texas ", "conference": "SEC", "scope": "All FBS teams",
        }, ratings)
        table_source = source.split('<div class="recovery-table">')[1]
        self.assertIn("Texas", table_source)
        self.assertNotIn("Texas Tech", table_source)
        self.assertNotIn("Ohio State", table_source)
        self.assertIn('value="SEC" selected', source)

    def test_weekly_search_matches_either_team_and_selected_week(self) -> None:
        fixture = pd.DataFrame([
            {"game_id": i, "display_week": week, "home_team": home, "away_team": away,
             "status": "Final", "start_date": "2026-09-01T16:00:00Z",
             "favorite_spread": 3, "home_win_probability": 0.6}
            for i, week, home, away in [(1, 1, "Texas", "Rice"), (2, 2, "Rice", "Texas"),
                                       (3, 2, "Georgia", "Alabama")]
        ])
        with patch("recovery_ui.read_csv", return_value=fixture):
            source = self.render_filtered(show_weekly, {"search": "texas", "week": "2"})
        table_source = source.split('<div class="recovery-table">')[1]
        self.assertEqual(table_source.count("<tbody>"), 1)
        self.assertEqual(table_source.count("<tr>"), 1)
        self.assertIn("Texas", table_source)
        self.assertNotIn("Georgia", table_source)
        self.assertIn('value="2" selected', source)

    def test_odds_search_week_and_both_edge_bounds(self) -> None:
        fixture = pd.DataFrame([
            {"market_status": "open_market", "display_week": week, "home_team": "Texas",
             "away_team": opponent, "absolute_edge_points": edge, "commence_time": "2026-09-01T16:00:00Z"}
            for week, opponent, edge in [(2, "Keep", 4), (2, "Too small", 1),
                                         (2, "Too large", 9), (1, "Wrong week", 4)]
        ])
        with patch("recovery_ui.read_csv", return_value=fixture):
            source = self.render_filtered(show_odds, {
                "search": "texas", "week": "2", "min_edge": "2.5", "max_edge": "5",
            })
        table_source = source.split('<div class="recovery-table">')[1]
        self.assertIn("Keep", table_source)
        for excluded in ["Too small", "Too large", "Wrong week"]:
            self.assertNotIn(excluded, table_source)
        self.assertIn('aria-label="Minimum edge">2.5</textarea>', source)
        self.assertIn('aria-label="Maximum edge">5</textarea>', source)

    def test_all_pages_are_preloaded_for_browser_only_navigation(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        with patch("recovery_ui.read_csv", wraps=read_csv) as reader:
            app.run(timeout=60)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.markdown), 1)
        source = app.markdown[0].value
        for page in PAGES:
            self.assertIn(f'href="#page-{page}"', source)
            self.assertIn(f'id="page-{page}"', source)
        self.assertEqual([call.args[0] for call in reader.call_args_list].count("cfbd_power_ratings_current.csv"), 1)

    def test_filters_on_one_page_do_not_empty_other_preloaded_pages(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        app.query_params.update({"page": "odds", "week": "All", "search": "NO SUCH TEAM"})
        app.run(timeout=60)
        self.assertFalse(app.exception)
        source = app.markdown[0].value
        weekly = re.search(r'id="page-weekly"[^>]*>(.*?)</section>', source, re.S).group(1)
        self.assertIn("<table", weekly)
        self.assertNotIn("No rows match", weekly)
        self.assertIn('id="page-odds" data-default=true', source)

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

from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).with_name("app.py")


class AppNavigationTests(unittest.TestCase):
    def test_startup_does_not_build_hidden_tabs(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        app.query_params["interface"] = "interactive"
        app.run(timeout=60)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["main_section"], "Rankings")
        self.assertTrue(app.tabs[0].children)
        for tab in app.tabs[1:]:
            self.assertFalse(tab.children, f"Hidden tab was built: {tab.label}")

    def test_every_tab_can_open_independently(self) -> None:
        app = AppTest.from_file(str(APP_PATH))
        app.query_params["interface"] = "interactive"
        app.run(timeout=60)
        labels = [tab.label for tab in app.tabs]
        for index, label in enumerate(labels):
            with self.subTest(tab=label):
                app.session_state["main_section"] = label
                app.run(timeout=60)
                self.assertFalse(app.exception, [error.message for error in app.exception])
                self.assertTrue(app.tabs[index].children, f"Selected tab is empty: {label}")


if __name__ == "__main__":
    unittest.main()

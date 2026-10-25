from __future__ import annotations

import io
import unittest
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from cfbd_client import CfbdClient


class CfbdClientTests(unittest.TestCase):
    def test_retries_transient_http_error(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"ok": true}')
        transient_error = HTTPError("https://example.test", 502, "Bad Gateway", None, None)
        client = CfbdClient(api_key="test", max_retries=2, retry_delay=0.1, request_timeout=5.0)

        with patch("cfbd_client.urlopen", side_effect=[transient_error, response]) as mocked_open:
            with patch("cfbd_client.time.sleep") as mocked_sleep:
                result = client.get("/games", year=2026)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mocked_open.call_count, 2)
        self.assertEqual(mocked_open.call_args.kwargs["timeout"], 5.0)
        mocked_sleep.assert_called_once_with(0.1)

    def test_does_not_retry_non_transient_http_error(self) -> None:
        permanent_error = HTTPError("https://example.test", 401, "Unauthorized", None, None)
        client = CfbdClient(api_key="test", max_retries=2, retry_delay=0.1)

        with patch("cfbd_client.urlopen", side_effect=permanent_error) as mocked_open:
            with patch("cfbd_client.time.sleep") as mocked_sleep:
                with self.assertRaises(HTTPError):
                    client.get("/games", year=2026)

        self.assertEqual(mocked_open.call_count, 1)
        mocked_sleep.assert_not_called()

    def test_retries_timeout(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"ok": true}')
        client = CfbdClient(api_key="test", max_retries=1, retry_delay=0.0, request_timeout=2.0)

        with patch("cfbd_client.urlopen", side_effect=[TimeoutError(), response]) as mocked_open:
            with patch("cfbd_client.time.sleep"):
                result = client.get("/rankings", year=2026)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mocked_open.call_count, 2)


if __name__ == "__main__":
    unittest.main()

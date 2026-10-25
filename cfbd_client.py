from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.collegefootballdata.com"
TOKEN_ENV_VARS = ("CFBD_API_KEY", "COLLEGEFOOTBALLDATA_API_KEY")
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


class CfbdClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        request_timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or self._load_api_key()
        self.base_url = base_url.rstrip("/")
        self.max_retries = max(0, max_retries)
        self.retry_delay = max(0.0, retry_delay)
        self.request_timeout = max(1.0, request_timeout)

    def _load_api_key(self) -> str:
        for env_var in TOKEN_ENV_VARS:
            value = os.getenv(env_var)
            if value:
                return value
        raise RuntimeError(
            "CFBD API key not found. Set CFBD_API_KEY or COLLEGEFOOTBALLDATA_API_KEY in your environment."
        )

    def get(self, path: str, **params: Any) -> Any:
        query = {key: value for key, value in params.items() if value is not None}
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"

        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "college-football-power-rankings",
            },
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.request_timeout) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code not in RETRYABLE_HTTP_CODES or attempt == self.max_retries:
                    raise
            except (URLError, TimeoutError):
                if attempt == self.max_retries:
                    raise

            delay = self.retry_delay * (2**attempt)
            print(f"CFBD request failed temporarily; retrying in {delay:.1f}s ({attempt + 1}/{self.max_retries}).")
            time.sleep(delay)

        raise RuntimeError("CFBD request exhausted retries without returning a response.")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

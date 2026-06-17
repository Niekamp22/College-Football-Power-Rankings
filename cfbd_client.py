from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.collegefootballdata.com"
TOKEN_ENV_VARS = ("CFBD_API_KEY", "COLLEGEFOOTBALLDATA_API_KEY")


class CfbdClient:
    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL) -> None:
        self.api_key = api_key or self._load_api_key()
        self.base_url = base_url.rstrip("/")

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
        with urlopen(request) as response:
            return json.load(response)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

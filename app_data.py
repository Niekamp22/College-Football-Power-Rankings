from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


def _file_version(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size, stat.st_ino


@st.cache_data(show_spinner=False, max_entries=64)
def _cached_csv(path: str, version: tuple[int, int, int]) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False, max_entries=64)
def _cached_json(path: str, version: tuple[int, int, int]) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False, max_entries=4)
def _cached_bytes(path: str, version: tuple[int, int, int]) -> bytes:
    return Path(path).read_bytes()


def load_csv(path: Path) -> pd.DataFrame:
    resolved = path.resolve()
    try:
        version = _file_version(resolved)
    except FileNotFoundError:
        return pd.DataFrame()
    # The version is part of the cache key; new published files bypass old entries.
    return _cached_csv(str(resolved), version)


def load_json(path: Path) -> Any:
    resolved = path.resolve()
    return _cached_json(str(resolved), _file_version(resolved))


def load_bytes(path: Path) -> bytes:
    resolved = path.resolve()
    return _cached_bytes(str(resolved), _file_version(resolved))

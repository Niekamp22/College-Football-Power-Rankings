from __future__ import annotations

from datetime import datetime
from typing import Any


def display_week_for_game(game: dict[str, Any]) -> int:
    """Label August games in CFBD Week 1 as Week 0 without mutating raw CFBD data."""
    week = int(game.get("week") or 0)
    if week != 1:
        return week

    start_date = game.get("startDate") or game.get("start_date")
    if not start_date:
        return week

    try:
        parsed_date = datetime.fromisoformat(str(start_date).replace("Z", "+00:00"))
    except ValueError:
        return week

    return 0 if parsed_date.month == 8 else week


def week_label(display_week: int | str) -> str:
    return f"Week {int(display_week)}"

from __future__ import annotations

import argparse
import csv
import json
import math
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DEFAULT_RATINGS_PATH = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_BACKTEST_PATH = Path("output/backtests/weekly_backtest_2025_regular.csv")
DEFAULT_UI_ROOT = Path("ui")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local UI for college football power ratings.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS_PATH)
    parser.add_argument("--backtest", type=Path, default=DEFAULT_BACKTEST_PATH)
    parser.add_argument("--ui-root", type=Path, default=DEFAULT_UI_ROOT)
    return parser.parse_args()


def parse_value(value: str):
    if value == "":
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: parse_value(value) for key, value in row.items()} for row in reader]


def win_probability(spread: float, margin_std_dev: float = 16.0) -> float:
    z_score = spread / margin_std_dev
    return 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))


class DashboardHandler(SimpleHTTPRequestHandler):
    ratings_path: Path
    backtest_path: Path
    ui_root: Path

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.ui_root), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ratings":
            self.serve_json(self.build_ratings_payload())
            return
        if parsed.path == "/api/backtest":
            self.serve_json(self.build_backtest_payload())
            return
        if parsed.path == "/api/matchup":
            self.serve_json(self.build_matchup_payload(parsed.query))
            return
        super().do_GET()

    def build_ratings_payload(self) -> dict:
        ratings = load_csv(self.ratings_path)
        conferences = sorted({row["conference"] for row in ratings if row.get("conference")})
        teams = sorted(row["team"] for row in ratings if row.get("team"))
        return {
            "ratings": ratings,
            "conferences": conferences,
            "teams": teams,
            "source": str(self.ratings_path),
        }

    def build_backtest_payload(self) -> dict:
        weekly_rows = load_csv(self.backtest_path)
        return {
            "weekly": weekly_rows,
            "source": str(self.backtest_path),
        }

    def build_matchup_payload(self, query: str) -> dict:
        params = parse_qs(query)
        team_a_name = params.get("team_a", [""])[0]
        team_b_name = params.get("team_b", [""])[0]
        ratings = load_csv(self.ratings_path)
        lookup = {str(row["team"]).lower(): row for row in ratings}

        if not team_a_name or not team_b_name:
            return {"error": "Both team_a and team_b are required."}

        team_a = lookup.get(team_a_name.lower())
        team_b = lookup.get(team_b_name.lower())
        if not team_a or not team_b:
            return {"error": "One or both teams could not be found."}

        spread = float(team_a["rating"]) - float(team_b["rating"])
        team_a_win_prob = win_probability(spread)
        return {
            "team_a": team_a["team"],
            "team_b": team_b["team"],
            "team_a_rating": round(float(team_a["rating"]), 2),
            "team_b_rating": round(float(team_b["rating"]), 2),
            "spread": round(spread, 2),
            "favorite": team_a["team"] if spread >= 0 else team_b["team"],
            "favorite_spread": round(abs(spread), 2),
            "team_a_win_probability": round(team_a_win_prob, 4),
            "team_b_win_probability": round(1 - team_a_win_prob, 4),
        }

    def serve_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    args = parse_args()
    handler_class = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {
            "ratings_path": args.ratings,
            "backtest_path": args.backtest,
            "ui_root": args.ui_root,
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    print(f"Serving dashboard at http://{args.host}:{args.port}")
    print(f"Ratings source: {args.ratings}")
    print(f"Backtest source: {args.backtest}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

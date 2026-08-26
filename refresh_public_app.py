from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_RATINGS_OUTPUT = Path("output/cfbd_power_ratings_2025.csv")
DEFAULT_RATINGS_EXCEL = Path("output/power_ratings_final.xlsx")
DEFAULT_BACKTEST_OUTPUTS = [
    Path("output/backtests/weekly_backtest_2025_regular.csv"),
    Path("output/backtests/game_backtest_2025_regular.csv"),
]
DEFAULT_PROJECTION_OUTPUTS = [
    Path("output/projections/projected_win_totals_2026.csv"),
    Path("output/projections/projected_games_2026.csv"),
    Path("output/projections/schedule_coverage_2026.csv"),
]
DEFAULT_ODDS_OUTPUT = Path("output/odds/ncaaf_game_odds_comparison.csv")
DEFAULT_MASTER_WORKBOOK = Path("output/power_ratings_master.xlsx")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh public Streamlit outputs and optionally push them to GitHub.")
    parser.add_argument("--ratings-year", type=int, default=2025)
    parser.add_argument("--projection-year", type=int, default=2026)
    parser.add_argument("--backtest-year", type=int, default=2025)
    parser.add_argument("--skip-cfbd-fetch", action="store_true")
    parser.add_argument("--skip-odds-fetch", action="store_true")
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--commit", action="store_true", help="Commit refreshed deployable outputs if anything changed.")
    parser.add_argument("--push", action="store_true", help="Push the commit to origin/main. Implies --commit.")
    return parser.parse_args()


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    print(subprocess.list2cmdline(command))
    subprocess.run(command, check=True, env=env)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is not set. Add it to the environment before running the refresh.")
    return value


def changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> None:
    args = parse_args()
    if args.push:
        args.commit = True

    ratings_features = Path(f"data/cfbd/processed/{args.ratings_year}/team_features.csv")
    ratings_lines = Path(f"data/cfbd/raw/{args.ratings_year}/lines.json")
    python = sys.executable

    if not args.skip_cfbd_fetch:
        require_env("CFBD_API_KEY")
        run([python, "fetch_cfbd_data.py", "ranking-inputs", "--year", str(args.ratings_year)])
        run([python, "fetch_cfbd_data.py", "games", "--year", str(args.projection_year), "--season-type", "regular"])

    run([python, "build_team_features.py", "--year", str(args.ratings_year)])
    run(
        [
            python,
            "power_rankings.py",
            "--features",
            str(ratings_features),
            "--lines",
            str(ratings_lines),
            "--save",
            str(DEFAULT_RATINGS_OUTPUT),
            "--excel",
            str(DEFAULT_RATINGS_EXCEL),
        ]
    )

    if not args.skip_backtest:
        run([python, "backtest_power_model.py", "--year", str(args.backtest_year), "--season-type", "regular", "--save-games"])

    run([python, "project_win_totals.py", "--season", str(args.projection_year)])

    if not args.skip_odds_fetch:
        require_env("ODDS_API_KEY")
        run([python, "sync_odds_api.py"])

    run([python, "export_master_workbook.py"])

    changes = changed_files()
    if not changes:
        print("No deployable changes detected.")
        return

    print()
    print("Changed files:")
    for line in changes:
        print(f"- {line}")

    if not args.commit:
        print()
        print("Refresh complete. Re-run with --commit or --push to publish these changes.")
        return

    files_to_commit = [
        ratings_features,
        DEFAULT_RATINGS_OUTPUT,
        DEFAULT_RATINGS_EXCEL,
        *DEFAULT_BACKTEST_OUTPUTS,
        *DEFAULT_PROJECTION_OUTPUTS,
        DEFAULT_ODDS_OUTPUT,
        DEFAULT_MASTER_WORKBOOK,
    ]
    existing_files = [str(path) for path in files_to_commit if path.exists()]
    run(["git", "add", *existing_files])

    commit_message = f"Weekly refresh {datetime.now().strftime('%Y-%m-%d')}"
    run(["git", "commit", "-m", commit_message])

    if args.push:
        run(["git", "push", "origin", "main"])


if __name__ == "__main__":
    main()

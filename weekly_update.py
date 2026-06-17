from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_WEEKLY_OUTPUT_ROOT = Path("output/weekly")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full weekly CFBD power ratings update pipeline.")
    parser.add_argument("--year", type=int, required=True, help="Season year to refresh.")
    parser.add_argument("--week", type=int, help="Optional week number used for output labeling.")
    parser.add_argument("--label", help="Optional custom label for the output snapshot folder.")
    parser.add_argument("--top", type=int, default=25, help="How many teams to print in the rankings step.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_WEEKLY_OUTPUT_ROOT,
        help="Root folder for weekly snapshot outputs.",
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Skip the CFBD download step.")
    parser.add_argument("--skip-features", action="store_true", help="Skip rebuilding the processed team features.")
    parser.add_argument("--skip-ratings", action="store_true", help="Skip rebuilding the final ratings outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands without executing them.")
    return parser.parse_args()


def build_label(args: argparse.Namespace) -> str:
    if args.label:
        return args.label
    if args.week is not None:
        return f"week_{args.week:02d}"
    return datetime.now().strftime("snapshot_%Y%m%d")


def run_command(command: list[str], dry_run: bool) -> None:
    rendered = subprocess.list2cmdline(command)
    print(rendered)
    if dry_run:
        return
    subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    label = build_label(args)

    raw_root = Path("data/cfbd/raw")
    processed_root = Path("data/cfbd/processed")
    output_dir = args.output_root / str(args.year) / label
    output_dir.mkdir(parents=True, exist_ok=True)

    features_path = processed_root / str(args.year) / "team_features.csv"
    lines_path = raw_root / str(args.year) / "lines.json"
    rankings_csv = output_dir / f"cfbd_power_ratings_{args.year}_{label}.csv"
    rankings_xlsx = output_dir / f"power_ratings_{args.year}_{label}.xlsx"

    commands: list[list[str]] = []
    if not args.skip_fetch:
        commands.append([sys.executable, "fetch_cfbd_data.py", "ranking-inputs", "--year", str(args.year)])
    if not args.skip_features:
        commands.append([sys.executable, "build_team_features.py", "--year", str(args.year)])
    if not args.skip_ratings:
        commands.append(
            [
                sys.executable,
                "power_rankings.py",
                "--features",
                str(features_path),
                "--lines",
                str(lines_path),
                "--top",
                str(args.top),
                "--save",
                str(rankings_csv),
                "--excel",
                str(rankings_xlsx),
            ]
        )

    manifest = {
        "year": args.year,
        "week": args.week,
        "label": label,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "features_path": str(features_path),
        "lines_path": str(lines_path),
        "rankings_csv": str(rankings_csv),
        "rankings_xlsx": str(rankings_xlsx),
        "dry_run": args.dry_run,
        "commands": commands,
    }

    print(f"Weekly update plan for {args.year} {label}")
    print()
    for command in commands:
        run_command(command, args.dry_run)

    if args.dry_run:
        manifest_path = output_dir / "manifest.dry_run.json"
    else:
        manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if not args.dry_run and rankings_csv.exists():
        latest_dir = args.output_root / str(args.year) / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rankings_csv, latest_dir / rankings_csv.name)
        if rankings_xlsx.exists():
            shutil.copy2(rankings_xlsx, latest_dir / rankings_xlsx.name)

    if args.dry_run:
        print()
        print(f"Dry run only. Wrote plan to {manifest_path}")
    else:
        print()
        print(f"Weekly update complete. Outputs saved in {output_dir}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a refresh validation report as GitHub-flavored Markdown.")
    parser.add_argument("report", type=Path, nargs="?", default=Path("output/refresh_status.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    print("## Weekly model refresh")
    print(f"**Status:** {report['status'].upper()}")
    print(f"**Generated:** {report['generated_at_utc']}")
    print("\n### Data checks")
    for key, value in report["stats"].items():
        print(f"- **{key.replace('_', ' ').title()}:** {value}")
    if report["warnings"]:
        print("\n### Warnings")
        for warning in report["warnings"]:
            print(f"- {warning}")
    if report["errors"]:
        print("\n### Errors")
        for error in report["errors"]:
            print(f"- {error}")


if __name__ == "__main__":
    main()

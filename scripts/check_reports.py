"""Check that `ai-eval report` produced every report file (used by CI; works on any OS).

Usage: python scripts/check_reports.py REPORT_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECTED = (
    "evaluation_results.csv",
    "evaluation_results.json",
    "pairwise_results.csv",
    "summary.md",
)


def main(report_dir: Path) -> int:
    problems = [
        f"missing or empty: {name}"
        for name in EXPECTED
        if not (report_dir / name).is_file() or (report_dir / name).stat().st_size == 0
    ]
    if not problems:
        meta = json.loads((report_dir / "evaluation_results.json").read_text("utf-8"))["metadata"]
        if meta["genuine_human_evaluations"] == 0 and "Demonstration data only" not in (
            report_dir / "summary.md"
        ).read_text("utf-8"):
            problems.append("summary.md lacks the demonstration-data banner")
    for problem in problems:
        print(f"::error::{problem}")
    print("reports OK" if not problems else f"{len(problems)} report problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))

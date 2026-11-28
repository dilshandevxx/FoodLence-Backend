#!/usr/bin/env python3
"""CLI for conservative FoodLence V4 unmatched vocabulary discovery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v4.discover_vocabulary import discover_vocabulary


def main() -> int:
    root = Path(__file__).parent / "foodlence_generated_v4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=root / "phase2" / "unmatched_candidates.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "phase6b1")
    parser.add_argument("--class-distribution", type=Path, default=root / "final_reports" / "v4_class_distribution.csv")
    args = parser.parse_args()
    report = discover_vocabulary(args.input, args.output_dir, taxonomy_distribution_path=args.class_distribution)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

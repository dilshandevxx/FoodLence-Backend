#!/usr/bin/env python3
"""Prepare a ranked shortlist and evidence-aware FoodLence review queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v4.prioritize_vocabulary import DEFAULT_LIMIT, prioritize_vocabulary


def main() -> int:
    base = Path(__file__).parent / "foodlence_generated_v4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=base / "phase6b1" / "vocabulary_candidates.csv")
    parser.add_argument("--output-dir", type=Path, default=base / "phase6b2")
    parser.add_argument("--class-distribution", type=Path, default=base / "final_reports" / "v4_class_distribution.csv")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="maximum shortlist size (default: 500)")
    args = parser.parse_args()
    report = prioritize_vocabulary(args.input, args.output_dir, args.class_distribution, args.limit)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

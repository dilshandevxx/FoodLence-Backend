"""CLI for the experimental FoodLence V4 exact-match ingredient recognizer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v4.audit_expanded_vocabulary import OUT, PHASE7A
from v4.recognize_ingredients import IngredientRecognizer, read_phrases_csv, write_results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phrase", help="one ingredient phrase")
    p.add_argument("--input-csv", type=Path, help="CSV containing ingredient phrases")
    p.add_argument("--column", help="phrase column name; otherwise common names are detected")
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--output", type=Path, help="optional results CSV path")
    p.add_argument("--json", action="store_true", help="emit results as JSON (stdout for a single phrase)")
    p.add_argument("--include-provenance", action="store_true", help="include source provenance references")
    p.add_argument("--phase7a-dir", type=Path, default=PHASE7A, help="Phase 7A vocabulary directory")
    args = p.parse_args()
    if bool(args.phrase is not None) == bool(args.input_csv):
        p.error("provide exactly one of --phrase or --input-csv")
    recognizer = IngredientRecognizer(args.phase7a_dir / "expanded_vocabulary.csv", args.phase7a_dir / "accepted_automatic_examples.csv")
    phrases = [args.phrase] if args.phrase is not None else read_phrases_csv(args.input_csv, args.column)
    results = [recognizer.recognize(x, args.include_provenance) for x in phrases]
    if args.json and args.phrase is not None and not args.output:
        print(json.dumps(results[0], ensure_ascii=False, indent=2))
        return 0
    output = args.output or (args.output_dir / ("recognition_results.json" if args.json else "recognition_results.csv"))
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.json:
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        write_results(output, results)
    print(json.dumps({"input_count": len(results), "output_file": str(output), "status_counts": {status: sum(r["match_status"] == status for r in results) for status in sorted({r["match_status"] for r in results})}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

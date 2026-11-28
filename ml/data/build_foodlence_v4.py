#!/usr/bin/env python3
"""FoodLence V4 taxonomy, extraction, integration, allergen, and audit CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v4.taxonomy import TAXONOMY
from v4.validate import validate_taxonomy
from v4.extract_sources import extract_sources
from v4.generate_variants import generate_candidates, PROVENANCE_FIELDS
from v4.validate import validate_generated
from v4.deduplicate import deduplicate
from v4.split_dataset import split_groups
from v4.hybrid import run as prepare_hybrid
from v4.allergens import process_allergens
import csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-taxonomy", action="store_true", help="validate the bundled canonical taxonomy")
    parser.add_argument("--extract-sources", action="store_true", help="extract source phrases and provenance")
    parser.add_argument("--input", type=Path, help="source CSV path")
    parser.add_argument("--output-dir", type=Path, help="Phase 2 output directory")
    parser.add_argument("--generate-candidates", action="store_true", help="generate controlled Phase 3B candidate pool")
    parser.add_argument("--prepare-splits", action="store_true", help="deduplicate and group-split Phase 3B candidates")
    parser.add_argument("--prepare-hybrid-splits", action="store_true", help="integrate Phase 2 source matches and Phase 3B synthetic candidates")
    parser.add_argument("--process-allergens", action="store_true", help="process separate multi-label allergen source")
    parser.add_argument("--generate-final-reports", action="store_true", help="audit corrected ingredient and separate allergen outputs")
    args = parser.parse_args()
    if args.validate_taxonomy:
        report = validate_taxonomy(TAXONOMY)
        print(json.dumps(report, indent=2))
        return 0 if report["structurally_valid"] else 1
    if args.extract_sources:
        from v4.extract_sources import DEFAULT_ROOT
        input_path = args.input or DEFAULT_ROOT / "raw" / "openfoodfacts_filtered.csv"
        output_dir = args.output_dir or DEFAULT_ROOT / "foodlence_generated_v4" / "phase2"
        print(json.dumps(extract_sources(input_path, output_dir), indent=2))
        return 0
    if args.generate_candidates:
        from pathlib import Path as _Path
        out = args.output_dir or _Path(__file__).parent / "foodlence_generated_v4" / "phase3b"
        out.mkdir(parents=True, exist_ok=False)
        rows = generate_candidates(TAXONOMY)
        result = validate_generated(rows, TAXONOMY)
        fields = list(PROVENANCE_FIELDS) + ["semantic_form"]
        for name, subset in (("synthetic_candidates.csv", rows), ("accepted_candidates.csv", rows), ("quarantined_candidates.csv", []), ("rejected_candidates.csv", []), ("combined_candidate_pool.csv", rows)):
            with (out / name).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(subset)
        import json as _json
        unique = len({r["normalized_text"] for r in rows})
        sem = len({(r["canonical_class_id"],r["semantic_form"]) for r in rows})
        report = {**result,"raw_generated_occurrences":len(rows),"unique_normalized_phrases":unique,"unique_semantic_forms":sem,
                  "accepted":len(rows) if result["structurally_valid"] else 0,"quarantined":0,"rejected":0,
                  "per_class":{c.class_id:sum(r['canonical_class_id']==c.class_id for r in rows) for c in TAXONOMY},
                  "semantic_verification":"unverified taxonomy-derived examples; no human review","seed":5104}
        (_Path(out)/"generation_report.json").write_text(_json.dumps(report,indent=2),encoding="utf-8")
        (_Path(out)/"validation_report.md").write_text(f"# V4 Phase 3B validation\n\nStructural validation: {result['structurally_valid']}\n\nThis does not establish semantic correctness. Taxonomy classes remain unverified and examples are not human-reviewed.\n",encoding="utf-8")
        (_Path(out)/"coverage_reconciliation.md").write_text("# Phase 2 class coverage reconciliation\n\nThe Phase 2 report's `candidate_counts_per_class` has 167 keys; the matched CSV has 179 occurrence rows, 167 unique normalized phrases, and 167 distinct class IDs. The earlier 151 figure was an incorrect summary. Phase 3A coverage also counts 167 distinct class IDs.\n",encoding="utf-8")
        print(_json.dumps(report,indent=2)); return 0 if result["structurally_valid"] else 1
    if args.prepare_splits:
        import csv as _csv
        out = args.output_dir or Path(__file__).parent / "foodlence_generated_v4" / "phase4"
        if out.exists(): raise SystemExit(f"Refusing to overwrite existing output: {out}")
        src=Path(__file__).parent/"foodlence_generated_v4"/"phase3b"/"combined_candidate_pool.csv"
        with src.open(encoding="utf-8",newline="") as f: rows=list(_csv.DictReader(f))
        for r in rows: r["is_synthetic"]=r["is_synthetic"].lower()=="true"
        dedup=deduplicate(rows); result=split_groups(dedup["accepted"])
        out.mkdir(parents=True)
        fields=list(rows[0]) + ["provenance_records","duplicate_occurrences","split","split_group"]
        def save(name, data):
            with (out/name).open("w",encoding="utf-8",newline="") as f:
                w=_csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(data)
        allrows=[r for part in result["splits"].values() for r in part]
        save("ingredients_all.csv",allrows);save("ingredients_provenance.csv",allrows)
        for part in ("train","validation","test"): save(f"ingredients_{part}.csv",result["splits"][part])
        save("ingredients_quarantined.csv",dedup["quarantined"])
        import json as _json
        (out/"deduplication_report.json").write_text(_json.dumps({k:v for k,v in dedup.items() if k not in ("accepted","quarantined")}|{"input_rows":len(rows),"unique_accepted":len(dedup["accepted"]),"quarantined":len(dedup["quarantined"])},indent=2),encoding="utf-8")
        (out/"split_report.json").write_text(_json.dumps({"seed":5104,"split_counts":result["split_counts"],"classes_per_split":result["classes_per_split"]},indent=2),encoding="utf-8")
        (out/"leakage_report.json").write_text(_json.dumps(result["leakage"],indent=2),encoding="utf-8")
        (out/"evaluation_limitations.md").write_text("# Evaluation limitations\n\nThese examples include synthetic and weak source-derived labels, an unverified taxonomy, no reliable product IDs, limited semantic diversity, possible distribution shift, and no human-reviewed ground truth. These splits are not independently verified benchmarks and do not establish real-world accuracy.\n",encoding="utf-8")
        print(_json.dumps({"dedup":len(dedup["accepted"]),"quarantined":len(dedup["quarantined"]),"splits":result["split_counts"],"leakage":result["leakage"]},indent=2));return 0
    if args.prepare_hybrid_splits:
        base=Path(__file__).parent/"foodlence_generated_v4"
        out=args.output_dir or base/"phase4b"
        print(json.dumps(prepare_hybrid(base/"phase2",base/"phase3b",out),indent=2));return 0
    if args.process_allergens:
        base=Path(__file__).parent
        source=args.input or base/"raw"/"allergies_10k.csv"
        out=args.output_dir or base/"foodlence_generated_v4"/"phase5"
        print(json.dumps(process_allergens(source,out),indent=2));return 0
    if args.generate_final_reports:
        from v4.final_reports import build_reports
        base=Path(__file__).parent/"foodlence_generated_v4"
        output=args.output_dir or base/"final_reports"
        report=build_reports(base/"phase4b_corrected",base/"phase5",output)
        print(json.dumps(report["validation"],indent=2));return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

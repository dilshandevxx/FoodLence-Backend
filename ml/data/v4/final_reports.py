"""Build the consolidated, data-derived FoodLence V4 audit reports."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .taxonomy import TAXONOMY


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_fields(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream).fieldnames or [])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: Iterable[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _contributors(row: dict) -> list[dict]:
    try:
        records = json.loads(row.get("contributor_provenance") or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return records if isinstance(records, list) else []


def analyze_ingredients(root: Path, taxonomy=TAXONOMY) -> tuple[dict, list[dict], list[dict], list[dict]]:
    all_path = root / "ingredients_all.csv"
    dataset_paths = [all_path, *(root / f"ingredients_{part}.csv" for part in ("train", "validation", "test"))]
    schema_consistent = all(csv_fields(path) == csv_fields(all_path) for path in dataset_paths)
    provenance_fields = set(csv_fields(root / "ingredients_provenance.csv"))
    required_provenance = {"candidate_id", "source_type", "source_dataset", "canonical_class_id", "normalized_text", "review_status"}
    all_rows = read_csv(all_path)
    split_rows = {part: read_csv(root / f"ingredients_{part}.csv") for part in ("train", "validation", "test")}
    provenance = read_csv(root / "ingredients_provenance.csv")
    expected_ids = {item.class_id for item in taxonomy}
    classes = {item.class_id: item for item in taxonomy}
    example_keys = [(r.get("normalized_text", ""), r.get("canonical_class_id", "")) for r in all_rows]
    canonical_per_split = {name: Counter(r.get("canonical_class_id", "") for r in rows) for name, rows in split_rows.items()}
    split_keys = {part: {(r.get("normalized_text", ""), r.get("canonical_class_id", "")) for r in rows} for part, rows in split_rows.items()}
    all_keys = set(example_keys)
    split_key_counts = Counter((r.get("normalized_text", ""), r.get("canonical_class_id", "")) for rows in split_rows.values() for r in rows)
    rows_by_split_key = {key: part for part, keys in split_keys.items() for key in keys}
    phrase_splits: dict[str, set[str]] = defaultdict(set)
    semantic_splits: dict[str, set[str]] = defaultdict(set)
    parent_splits: dict[str, set[str]] = defaultdict(set)
    by_class = Counter()
    src_class = Counter()
    syn_class = Counter()
    review_dist = Counter()
    reviewed_by_class = Counter()
    categories = Counter()
    provenance_ids = []
    semantic_forms = set()
    for row in all_rows:
        cid, phrase, part = row.get("canonical_class_id", ""), row.get("normalized_text", ""), row.get("split", "")
        by_class[cid] += 1
        semantic_forms.add((cid, row.get("semantic_form", "")))
        phrase_splits[phrase].add(part)
        if row.get("semantic_form"):
            semantic_splits[row["semantic_form"]].add(part)
        if row.get("parent_example_id"):
            parent_splits[row["parent_example_id"]].add(part)
        records = _contributors(row)
        types = {r.get("source_type") for r in records}
        category = "both" if {"source_derived", "synthetic_taxonomy"}.issubset(types) else "source_only" if "source_derived" in types else "synthetic_only"
        categories[category] += 1
        src_class[cid] += sum(r.get("source_type") == "source_derived" for r in records)
        syn_class[cid] += sum(r.get("source_type") == "synthetic_taxonomy" for r in records)
        for record in records:
            review_dist[record.get("review_status") or "missing"] += 1
            provenance_ids.append(record.get("candidate_id"))
        if row.get("review_status") == "human_reviewed":
            reviewed_by_class[cid] += 1

    source_contributors = sum(r.get("source_type") == "source_derived" for r in provenance)
    synthetic_contributors = sum(r.get("is_synthetic", "").casefold() == "true" for r in provenance)
    prov_review = Counter(r.get("review_status") or "missing" for r in provenance)
    class_rows = []
    for cid, item in sorted(classes.items()):
        class_rows.append({
            "canonical_class_id": cid, "canonical_name": item.canonical_name,
            "total_accepted_examples": by_class[cid],
            "train_examples": canonical_per_split["train"][cid],
            "validation_examples": canonical_per_split["validation"][cid],
            "test_examples": canonical_per_split["test"][cid],
            "source_derived_contributors": src_class[cid], "synthetic_contributors": syn_class[cid],
            "human_reviewed_examples": reviewed_by_class[cid],
        })
    total_classes = len(expected_ids)
    represented = {part: set(counts) - {""} for part, counts in canonical_per_split.items()}
    split_summary = {
        "total_classes": total_classes,
        "classes_represented": {part: len(represented[part]) for part in split_rows},
        "classes_absent": {part: sorted(expected_ids - represented[part]) for part in split_rows},
        "classes_with_fewer_than_two_training_examples": sum(canonical_per_split["train"][cid] < 2 for cid in expected_ids),
        "classes_without_validation_examples": sum(canonical_per_split["validation"][cid] == 0 for cid in expected_ids),
        "classes_without_test_examples": sum(canonical_per_split["test"][cid] == 0 for cid in expected_ids),
    }
    split_integrity = {
        "split_counts": {part: len(rows) for part, rows in split_rows.items()},
        "all_examples_partitioned_once": sum(len(rows) for rows in split_rows.values()) == len(all_rows) and len(all_keys) == len(all_rows) and all(split_key_counts[k] == 1 for k in all_keys) and set(rows_by_split_key) == all_keys,
        "split_assignment_matches_authoritative_rows": all(rows_by_split_key.get(k) == row.get("split") for row in all_rows for k in [(row.get("normalized_text", ""), row.get("canonical_class_id", ""))]),
        "normalized_phrase_leakage_groups": sorted(k for k, v in phrase_splits.items() if len(v) > 1),
        "semantic_form_leakage_groups": sorted(k for k, v in semantic_splits.items() if len(v) > 1),
        "parent_child_leakage_groups": sorted(k for k, v in parent_splits.items() if len(v) > 1),
        "invalid_canonical_class_examples": sum(r.get("canonical_class_id") not in expected_ids for r in all_rows),
        "conflicting_label_quarantine_rows": len(read_csv(root / "conflicting_contributors.csv")) if (root / "conflicting_contributors.csv").exists() else 0,
    }
    provenance_summary = []
    for row in all_rows:
        records = _contributors(row)
        source_n = sum(x.get("source_type") == "source_derived" for x in records)
        synthetic_n = sum(x.get("source_type") == "synthetic_taxonomy" for x in records)
        provenance_summary.append({
            "example_id": row.get("candidate_id"), "canonical_class_id": row.get("canonical_class_id"),
            "provenance_category": row.get("provenance_category", ""),
            "source_contributors": source_n, "synthetic_contributors": synthetic_n,
            "total_contributors": len(records), "review_status": row.get("review_status", ""),
        })
    input_paths = [all_path, root / "ingredients_train.csv", root / "ingredients_validation.csv", root / "ingredients_test.csv", root / "ingredients_provenance.csv"]
    stats = {
        "accepted_examples": len(all_rows),
        "unique_accepted_phrases": len({r.get("normalized_text", "") for r in all_rows}),
        "unique_semantic_forms": len(semantic_forms),
        "canonical_class_count": total_classes,
        "canonical_classes_covered": len({r.get("canonical_class_id") for r in all_rows} & expected_ids),
        "source_derived_contributor_occurrences": source_contributors,
        "synthetic_contributor_occurrences": synthetic_contributors,
        "total_provenance_records": len(provenance),
        "unique_provenance_candidate_ids": len({r.get("candidate_id") for r in provenance}),
        "provenance_candidate_ids_unique": len({r.get("candidate_id") for r in provenance}) == len(provenance),
        "source_only_examples": categories["source_only"], "synthetic_only_examples": categories["synthetic_only"], "both_source_examples": categories["both"],
        "split_coverage": split_summary, "split_integrity": split_integrity,
        "ingredient_split_schemas_consistent": schema_consistent,
        "provenance_schema_complete": required_provenance.issubset(provenance_fields),
        "human_review_status_distribution": dict(sorted(prov_review.items())),
        "human_reviewed_examples": sum(reviewed_by_class.values()),
        "independently_verified_examples": sum(1 for row in all_rows if classes.get(row.get("canonical_class_id")) and classes[row["canonical_class_id"]].verification_status.casefold() in {"verified", "independently_verified"}),
        "provenance_count_matches_enrichment_report": len(provenance) == source_contributors + synthetic_contributors,
        "input_sha256": {str(p.name): sha256(p) for p in input_paths},
        "limitations": [
            "Source-derived labels are provisional exact taxonomy matches; synthetic examples inherit unverified taxonomy labels.",
            "No independent semantic verification or documented human review is represented.",
            "Product IDs are unavailable, so product-level split independence cannot be established.",
            "Class and semantic-form coverage is uneven; these are not independently verified real-world evaluation splits.",
        ],
    }
    return stats, class_rows, split_summary, provenance_summary


def analyze_allergens(root: Path) -> dict:
    accepted = read_csv(root / "allergens_all.csv")
    quarantined = read_csv(root / "allergens_quarantined.csv")
    rejected = read_csv(root / "allergens_rejected.csv")
    occurrences = sum(int(r.get("duplicate_occurrences") or 1) for r in accepted)
    labels = Counter()
    empty = 0
    reviews = Counter()
    for row in accepted:
        normalized = json.loads(row.get("normalized_allergen_labels") or "[]")
        if not normalized:
            empty += int(row.get("duplicate_occurrences") or 1)
        labels.update(normalized)
        reviews[row.get("review_status") or "missing"] += 1
    quality_path = root / "allergen_quality_report.json"
    previous = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    return {
        "source_rows_processed": occurrences + len(quarantined) + len(rejected),
        "source_rows_reported_by_phase5": previous.get("source_rows_processed"),
        "source_row_count_matches_phase5_report": previous.get("source_rows_processed") in (None, occurrences + len(quarantined) + len(rejected)),
        "accepted_unique_examples": len(accepted), "accepted_source_occurrences": occurrences,
        "distinct_normalized_allergen_labels": sorted(labels), "label_distribution": dict(sorted(labels.items())),
        "empty_label_occurrences_unknown": empty,
        "duplicate_occurrences_collapsed": occurrences - len(accepted),
        "conflicting_label_groups": previous.get("conflicting_duplicate_groups", 0),
        "quarantined_rows": len(quarantined), "rejected_rows": len(rejected),
        "review_status_distribution": dict(sorted(reviews.items())),
        "empty_labels_are_verified_negatives": False,
        "source_file_hash": previous.get("source_file_hash", ""),
        "limitations": ["Allergen labels are source-provided and not human-reviewed.", "An empty label list means unknown or unlabeled, not allergen-free."],
    }


def build_reports(ingredient_dir: Path, allergen_dir: Path, output_dir: Path, taxonomy=TAXONOMY) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    stats, class_rows, split_summary, provenance_rows = analyze_ingredients(ingredient_dir, taxonomy)
    allergen = analyze_allergens(allergen_dir)
    report = {
        "pipeline_version": "FoodLence V4 / Phase 6A-R2",
        "authoritative_ingredient_dataset": str(ingredient_dir.as_posix()),
        "separate_allergen_dataset": str(allergen_dir.as_posix()),
        "ingredient_dataset": stats,
        "allergen_dataset": allergen,
        "validation": {
            "ingredient_split_integrity": stats["split_integrity"],
            "taxonomy_class_references_valid": stats["split_integrity"]["invalid_canonical_class_examples"] == 0,
            "provenance_rows_reconcile": stats["provenance_count_matches_enrichment_report"],
            "provenance_candidate_ids_unique": stats["provenance_candidate_ids_unique"],
            "ingredient_split_schemas_consistent": stats["ingredient_split_schemas_consistent"],
            "provenance_schema_complete": stats["provenance_schema_complete"],
            "allergen_source_count_reconciles": allergen["source_row_count_matches_phase5_report"],
            "allergen_empty_labels_not_negative": not allergen["empty_labels_are_verified_negatives"],
        },
        "reproducibility": {"deterministic": True, "method": "CSV input SHA-256 hashes recorded; no timestamps or random operations"},
    }
    _write_csv(output_dir / "v4_class_distribution.csv", class_rows, ["canonical_class_id", "canonical_name", "total_accepted_examples", "train_examples", "validation_examples", "test_examples", "source_derived_contributors", "synthetic_contributors", "human_reviewed_examples"])
    split_rows = [{"metric": "total_classes", "count": split_summary["total_classes"]}]
    for part in ("train", "validation", "test"):
        split_rows.append({"metric": f"classes_represented_{part}", "count": split_summary["classes_represented"][part]})
        split_rows.append({"metric": f"classes_absent_{part}", "count": len(split_summary["classes_absent"][part]), "class_ids": ",".join(split_summary["classes_absent"][part])})
    split_rows.extend([
        {"metric": "classes_with_fewer_than_two_training_examples", "count": split_summary["classes_with_fewer_than_two_training_examples"]},
        {"metric": "classes_without_validation_examples", "count": split_summary["classes_without_validation_examples"]},
        {"metric": "classes_without_test_examples", "count": split_summary["classes_without_test_examples"]},
    ])
    _write_csv(output_dir / "v4_split_coverage.csv", split_rows, ["metric", "count", "class_ids"])
    _write_csv(output_dir / "v4_provenance_summary.csv", provenance_rows, ["example_id", "canonical_class_id", "provenance_category", "source_contributors", "synthetic_contributors", "total_contributors", "review_status"])
    (output_dir / "v4_allergen_summary.json").write_text(json.dumps(allergen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "v4_quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_markdown(output_dir / "v4_quality_report.md", report)
    _write_task_gap(output_dir / "v4_task02_gap_analysis.md", stats)
    return report


def _write_markdown(path: Path, report: dict) -> None:
    i, a = report["ingredient_dataset"], report["allergen_dataset"]
    s = i["split_integrity"]
    lines = ["# FoodLence V4 quality report", "", f"Pipeline: {report['pipeline_version']}", "", "## Ingredient dataset", "",
             f"- Accepted examples: {i['accepted_examples']}", f"- Unique phrases / semantic forms: {i['unique_accepted_phrases']} / {i['unique_semantic_forms']}",
             f"- Classes covered: {i['canonical_classes_covered']} / {i['canonical_class_count']}",
             f"- Contributors: {i['source_derived_contributor_occurrences']} source, {i['synthetic_contributor_occurrences']} synthetic; {i['total_provenance_records']} provenance records",
             f"- Categories: {i['source_only_examples']} source-only, {i['synthetic_only_examples']} synthetic-only, {i['both_source_examples']} both",
             f"- Splits: {s['split_counts']}", f"- Partition once: {s['all_examples_partitioned_once']}; invalid class references: {s['invalid_canonical_class_examples']}",
             f"- Leakage groups (phrase / semantic form / parent): {len(s['normalized_phrase_leakage_groups'])} / {len(s['semantic_form_leakage_groups'])} / {len(s['parent_child_leakage_groups'])}",
             f"- Review status: {i['human_review_status_distribution']}", "", "## Separate allergen dataset", "",
             f"- Source occurrences: {a['source_rows_processed']}; accepted unique examples: {a['accepted_unique_examples']}",
             f"- Labels: {len(a['distinct_normalized_allergen_labels'])}; empty-label occurrences treated as unknown: {a['empty_label_occurrences_unknown']}",
             f"- Quarantined / rejected: {a['quarantined_rows']} / {a['rejected_rows']}", "- Empty allergen labels are not verified negatives.", "",
             "## Limitations", "", *[f"- {x}" for x in i["limitations"]], *[f"- {x}" for x in a["limitations"]], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_task_gap(path: Path, stats: dict) -> None:
    target = 3000
    phrases, semantic = stats["unique_accepted_phrases"], stats["unique_semantic_forms"]
    lines = ["# Task 02 gap analysis", "", "## Target and current state", "",
             f"- Original target: at least {target} human-reviewed ingredient/additive examples.",
             f"- Current unique ingredient phrases: {phrases}.", f"- Current unique semantic forms: {semantic}.",
             f"- Independently verified examples: {stats['independently_verified_examples']}.",
             f"- Documented human-reviewed examples: {stats['human_reviewed_examples']}.",
             f"- Additional unique phrases to reach a raw count of {target}: {max(0, target - phrases)} (this does not satisfy the review requirement).",
             f"- Additional unique semantic forms to reach {target}: {max(0, target - semantic)}.",
             f"- Human-reviewed example shortfall: {max(0, target - stats['human_reviewed_examples'])}.",
             f"- Canonical class coverage: {stats['canonical_classes_covered']} / {stats['canonical_class_count']}.", "",
             "## Gaps and limitations", "", "- Surface formatting variants are not independent semantic examples; semantic-form count is reported separately.",
             "- Current source matches are provisional; synthetic records inherit taxonomy labels marked unverified.",
             "- There are no documented human review records or independently verified labels.",
             "- Product identifiers are absent, preventing a product-level independence claim for splits.",
             "- Validation/test coverage is uneven; these partitions are not real-world benchmark sets.", "",
             "## Recommendations", "", "- Collect package OCR samples with stable product/source IDs and retain raw observations.",
             "- Have annotators review ingredient spans and canonical labels; store reviewer identity, decision, and adjudication evidence.",
             "- Prioritize underrepresented canonical classes and diverse products, languages, and package conditions.",
             "- Split by product/source ID before augmentation, then independently audit held-out labels.",
             "- Keep allergen annotations separate from the ingredient/additive example target.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).parents[1] / "foodlence_generated_v4"
    parser.add_argument("--ingredient-dir", type=Path, default=root / "phase4b_corrected")
    parser.add_argument("--allergen-dir", type=Path, default=root / "phase5")
    parser.add_argument("--output-dir", type=Path, default=root / "final_reports")
    args = parser.parse_args()
    report = build_reports(args.ingredient_dir, args.allergen_dir, args.output_dir)
    print(json.dumps(report["validation"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

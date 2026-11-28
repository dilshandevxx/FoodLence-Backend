"""Package and integrity-audit the existing FoodLence V4 dataset artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from .taxonomy import TAXONOMY

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "foodlence_generated_v4"
PACKAGE_NAME = "final_package"
PACKAGE_VERSION = "FoodLence V4 Final Package 1.0"
COMPONENT_DIRS = {
    "phase4b_corrected": "ingredients",
    "phase5": "allergens",
    "final_reports": "reports/phase6a",
    "phase6b1": "vocabulary/discovery",
    "phase6b2": "vocabulary/prioritization",
    "phase6b3": "vocabulary/review/phase6b3",
    "phase6b4": "vocabulary/review/phase6b4",
    "phase7a": "vocabulary/expansion",
    "phase7b": "vocabulary/audit",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_info(path: Path) -> tuple[list[str], int, list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        data = list(reader)
    return header, len(data), data


def _component(source_rel: Path) -> str:
    parts = source_rel.parts
    return {"phase4b_corrected": "ingredients", "phase5": "allergens", "final_reports": "reports",
            "phase6b1": "vocabulary", "phase6b2": "vocabulary", "phase6b3": "vocabulary",
            "phase6b4": "vocabulary", "phase7a": "vocabulary", "phase7b": "recognition"}.get(parts[0], "reports")


def collect_files(source_root: Path) -> dict[Path, Path]:
    """Map package-relative paths to source artifacts; generated outputs are copied unchanged."""
    found: dict[Path, Path] = {}
    for source_dir, target_dir in COMPONENT_DIRS.items():
        base = source_root / source_dir
        if not base.is_dir():
            continue
        for source in sorted(p for p in base.rglob("*") if p.is_file()):
            relative = source.relative_to(base)
            target = Path(target_dir) / relative
            # Phase 7B recognition reports are also copied into a focused component.
            if source_dir == "phase7b":
                found[Path("recognition") / relative] = source
            found[target] = source
    return found


def _source_provenance(source_rel: Path) -> str:
    first = source_rel.parts[0] if source_rel.parts else ""
    return {
        "phase4b_corrected": "Hybrid source-derived Open Food Facts and controlled synthetic records; contributor references are retained in the packaged provenance CSVs.",
        "phase5": "Source-provided labels from allergies_10k.csv; source hash and row references are retained; empty labels remain unknown.",
        "phase6b1": "Vocabulary discovery from local source-derived phrase occurrences; not human-reviewed ground truth.",
        "phase6b2": "Prioritization and reference evidence records for future human review; not activated labels.",
        "phase6b3": "Review workflow exports; only actual decision records, if any, are represented as such.",
        "phase6b4": "Evidence pilot and blank example review template; template fields do not constitute completed review.",
        "phase7a": "Automatically processed source occurrences and controlled existing synthetic forms, with evidence tiers and source provenance.",
        "phase7b": "Descriptive audit and deterministic recognizer samples derived from Phase 7A vocabulary and examples.",
        "final_reports": "Consolidated reports derived from existing Phase 4B corrected and Phase 5 outputs.",
    }.get(first, "FoodLence V4 package documentation or generated metadata.")


def _verification(source_rel: Path) -> str:
    first = source_rel.parts[0] if source_rel.parts else ""
    if first in {"phase6b1", "phase6b2", "phase6b3", "phase6b4"}:
        return "review_aid_only_not_scientifically_verified"
    if first in {"phase4b_corrected", "phase5", "phase7a", "phase7b"}:
        return "structurally_processed_not_independently_verified"
    return "descriptive_or_documentary_not_ground_truth"


def _review_status(path: Path, header: list[str], records: list[dict[str, str]] | None) -> str:
    if records is not None and "review_status" in header:
        statuses = {r.get("review_status", "").strip() for r in records}
        statuses.discard("")
        if statuses == {"not_human_reviewed"}:
            return "not_human_reviewed"
        return ";".join(sorted(statuses)) if statuses else "no_review_status_recorded"
    if "review" in str(path).casefold() or "template" in str(path).casefold():
        return "review_workflow_artifact_not_evidence_of_completed_review"
    return "not_applicable"


def _schema_version(path: Path, header: list[str], records: list[dict[str, str]] | None) -> str:
    if path.suffix.casefold() == ".csv":
        versions = sorted({r.get("dataset_version", "").strip() for r in (records or []) if r.get("dataset_version", "").strip()})
        return ";".join(versions) if versions else "csv-header-v1"
    return "markdown-v1" if path.suffix.casefold() == ".md" else "json-v1" if path.suffix.casefold() == ".json" else "file-v1"


def validate_source_artifacts(source_root: Path) -> dict:
    """Run final consistency checks. Failures are returned, never repaired silently."""
    issues: list[dict] = []
    metrics: dict = {}
    required = [
        "phase4b_corrected/ingredients_all.csv", "phase4b_corrected/ingredients_train.csv",
        "phase4b_corrected/ingredients_validation.csv", "phase4b_corrected/ingredients_test.csv",
        "phase4b_corrected/ingredients_provenance.csv", "phase5/allergens_all.csv",
        "phase5/allergens_quarantined.csv", "phase5/allergens_rejected.csv",
        "phase5/allergen_quality_report.json",
        "phase7a/expanded_vocabulary.csv", "phase7a/accepted_automatic_examples.csv",
        "phase7a/unresolved_candidates.csv", "phase7a/vocabulary_expansion_report.json", "phase7b/ambiguous_terms.csv",
        "phase7b/sample_recognition_results.csv", "final_reports/v4_quality_report.json",
        "final_reports/v4_allergen_summary.json",
    ]
    for item in required:
        if not (source_root / item).is_file():
            issues.append({"code": "required_file_missing", "path": item})
    if issues:
        return {"passed": False, "issues": issues, "metrics": metrics}

    all_path = source_root / "phase4b_corrected/ingredients_all.csv"
    header, _, all_rows = csv_info(all_path)
    required_baseline_fields = {"candidate_id", "normalized_text", "canonical_class_id", "source_contributions", "provenance_records", "semantic_form", "split", "split_group", "review_status"}
    missing = sorted(required_baseline_fields - set(header))
    if missing:
        issues.append({"code": "baseline_schema_missing_fields", "fields": missing})
    id_field = "candidate_id"
    all_ids = [r.get(id_field, "") for r in all_rows]
    if len(all_ids) != len(set(all_ids)) or any(not x for x in all_ids):
        issues.append({"code": "baseline_example_id_not_unique_or_missing"})
    expected_fields = set(header)
    partition_rows: list[dict[str, str]] = []
    partition_ids: list[str] = []
    split_names = {"ingredients_train.csv": "train", "ingredients_validation.csv": "validation", "ingredients_test.csv": "test"}
    for filename, expected_split in split_names.items():
        file_header, _, rows = csv_info(source_root / "phase4b_corrected" / filename)
        if set(file_header) != expected_fields:
            issues.append({"code": "baseline_split_schema_mismatch", "file": filename})
        if any(r.get("split") != expected_split for r in rows):
            issues.append({"code": "baseline_split_value_mismatch", "file": filename})
        partition_rows.extend(rows)
        partition_ids.extend(r.get(id_field, "") for r in rows)
    if Counter(partition_ids) != Counter(all_ids):
        issues.append({"code": "baseline_split_partition_mismatch", "all_count": len(all_ids), "partition_count": len(partition_ids)})
    invalid_baseline_classes = sorted({r.get("canonical_class_id", "") for r in all_rows} - {c.class_id for c in TAXONOMY})
    if invalid_baseline_classes:
        issues.append({"code": "invalid_baseline_canonical_class_reference", "class_ids": invalid_baseline_classes})

    group_splits: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in partition_rows:
        for key in ("normalized_text", "semantic_form", "split_group"):
            if row.get(key):
                group_splits[(key, row[key])].add(row.get("split", ""))
    leaked = [{"group_type": k[0], "group": k[1], "splits": sorted(v)} for k, v in group_splits.items() if len(v) > 1]
    if leaked:
        issues.append({"code": "known_group_split_leakage", "groups": leaked[:20], "group_count": len(leaked)})

    provenance_header, _, provenance_rows = csv_info(source_root / "phase4b_corrected/ingredients_provenance.csv")
    required_provenance_fields = {"accepted_example_id", "candidate_id", "source_type", "source_dataset", "source_reference", "source_row_id", "normalized_text", "review_status"}
    if required_provenance_fields - set(provenance_header):
        issues.append({"code": "provenance_schema_missing_fields", "fields": sorted(required_provenance_fields-set(provenance_header))})
    contributor_ids = [r.get("candidate_id", "") for r in provenance_rows]
    if len(contributor_ids) != len(set(contributor_ids)) or any(not x for x in contributor_ids):
        issues.append({"code": "provenance_candidate_id_not_unique_or_missing"})
    contributors_by_example: dict[str, set[str]] = defaultdict(set)
    for r in provenance_rows:
        contributors_by_example[r.get("accepted_example_id", "")].add(r.get("candidate_id", ""))
    provenance_rows_by_example: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in provenance_rows:
        provenance_rows_by_example[r.get("accepted_example_id", "")].append(r)
    contributor_set = set(contributor_ids)
    for row in all_rows:
        aid = row.get("candidate_id", "")
        claimed = {x for x in row.get("provenance_records", "").split("|") if x}
        if not claimed or not claimed.issubset(contributor_set) or not claimed.issubset(contributors_by_example.get(aid, set())):
            issues.append({"code": "baseline_provenance_reference_invalid", "example_id": aid})
            if len([i for i in issues if i["code"] == "baseline_provenance_reference_invalid"]) >= 20:
                break
        expected_contributions = {"source_derived" if r.get("source_type") == "source_derived" else "synthetic_taxonomy" for r in provenance_rows_by_example.get(aid, [])}
        reported_contributions = {x for x in row.get("source_contributions", "").split("|") if x}
        if expected_contributions != reported_contributions:
            issues.append({"code": "baseline_source_synthetic_contribution_mismatch", "example_id": aid})
    missing_source_keys = [r.get("candidate_id", "") for r in provenance_rows if r.get("source_type") == "source_derived" and any(not r.get(k, "").strip() for k in ("source_dataset", "source_file_hash", "source_row_id"))]
    if missing_source_keys:
        issues.append({"code": "baseline_source_contributor_provenance_incomplete", "candidate_ids": missing_source_keys[:20], "count": len(missing_source_keys)})
    split_by_id = {r.get("candidate_id", ""): r.get("split", "") for r in all_rows}
    bad_parents = [{"candidate_id": r.get("candidate_id", ""), "parent_example_id": r.get("parent_example_id", ""), "child_split": r.get("split", ""), "parent_split": split_by_id[r.get("parent_example_id", "")]} for r in all_rows if r.get("parent_example_id") in split_by_id and split_by_id[r.get("parent_example_id", "")] != r.get("split", "")]
    if bad_parents:
        issues.append({"code": "known_parent_child_split_leakage", "examples": bad_parents[:20], "count": len(bad_parents)})

    reviewed_files = [source_root / "phase4b_corrected/ingredients_all.csv", source_root / "phase4b_corrected/ingredients_provenance.csv", source_root / "phase5/allergens_all.csv", source_root / "phase7a/accepted_automatic_examples.csv"]
    human_reviewed = 0
    for path in reviewed_files:
        _, _, rows = csv_info(path)
        human_reviewed += sum(r.get("review_status", "") == "human_reviewed" for r in rows)
        if any(r.get("review_status") not in {"not_human_reviewed", ""} for r in rows):
            # Nonblank non-human status is acceptable in workflow exports, but not in accepted examples.
            if path.name in {"ingredients_all.csv", "ingredients_provenance.csv", "allergens_all.csv", "accepted_automatic_examples.csv"}:
                issues.append({"code": "unsupported_review_status_in_accepted_dataset", "file": str(path.relative_to(source_root))})
    if human_reviewed:
        issues.append({"code": "human_review_claim_found", "count": human_reviewed})

    vocab_header, _, vocab_rows = csv_info(source_root / "phase7a/expanded_vocabulary.csv")
    if {"term", "normalized_term", "entry_kind", "class_id", "canonical_name", "evidence_tier", "review_status"} - set(vocab_header):
        issues.append({"code": "expanded_vocabulary_schema_missing_fields", "fields": sorted({"term", "normalized_term", "entry_kind", "class_id", "canonical_name", "evidence_tier", "review_status"}-set(vocab_header))})
    canonical_ids = {r.get("class_id", "") for r in vocab_rows if r.get("entry_kind") == "canonical_class"}
    vocabulary_class_ids = {r.get("class_id", "") for r in vocab_rows if r.get("class_id", "")}
    expected_canonical_ids = {c.class_id for c in TAXONOMY}
    if canonical_ids != expected_canonical_ids:
        issues.append({"code": "canonical_taxonomy_ids_changed_or_incomplete", "missing": sorted(expected_canonical_ids-canonical_ids), "extra": sorted(canonical_ids-expected_canonical_ids)})
    accepted_header, _, accepted_rows = csv_info(source_root / "phase7a/accepted_automatic_examples.csv")
    required_accepted_fields = {"example_id", "normalized_text", "proposed_class_id", "source_type", "is_synthetic", "evidence_tier", "source_dataset", "source_file_hash", "source_row_id", "source_reference", "review_status"}
    if required_accepted_fields - set(accepted_header):
        issues.append({"code": "phase7a_accepted_schema_missing_fields", "fields": sorted(required_accepted_fields-set(accepted_header))})
    accepted_ids = [r.get("example_id", "") for r in accepted_rows]
    if len(accepted_ids) != len(set(accepted_ids)) or any(not x for x in accepted_ids):
        issues.append({"code": "phase7a_accepted_example_ids_not_unique_or_missing"})
    conversion_errors = []
    invalid_proposed_ids = []
    for row in accepted_rows:
        synthetic = row.get("is_synthetic", "").casefold() == "true"
        if (synthetic and row.get("source_type") != "synthetic") or (not synthetic and row.get("source_type") != "source_derived"):
            conversion_errors.append(row.get("example_id", ""))
        if row.get("proposed_class_id", "") not in vocabulary_class_ids:
            invalid_proposed_ids.append(row.get("example_id", ""))
        if row.get("source_type") == "source_derived" and any(not row.get(k, "").strip() for k in ("source_dataset", "source_file_hash", "source_row_id", "source_reference")):
            issues.append({"code": "phase7a_source_provenance_incomplete", "example_id": row.get("example_id", "")})
    if conversion_errors:
        issues.append({"code": "phase7a_source_synthetic_flag_disagreement", "examples": conversion_errors[:20], "count": len(conversion_errors)})
    if invalid_proposed_ids:
        issues.append({"code": "phase7a_invalid_vocabulary_class_reference", "examples": invalid_proposed_ids[:20], "count": len(invalid_proposed_ids)})

    phase7a_report = json.loads((source_root / "phase7a/vocabulary_expansion_report.json").read_text(encoding="utf-8"))
    phase7a_counts = Counter(r.get("source_type", "") for r in accepted_rows)
    if len(accepted_rows) != phase7a_report.get("accepted_automatic_example_count") or phase7a_counts.get("source_derived", 0) != phase7a_report.get("accepted_source_derived_count") or phase7a_counts.get("synthetic", 0) != phase7a_report.get("accepted_synthetic_count"):
        issues.append({"code": "phase7a_accepted_counts_do_not_reconcile"})
    _, vocabulary_count, _ = csv_info(source_root / "phase7a/expanded_vocabulary.csv")
    if vocabulary_count != phase7a_report.get("vocabulary_terms_after"):
        issues.append({"code": "phase7a_vocabulary_count_does_not_reconcile", "actual": vocabulary_count, "reported": phase7a_report.get("vocabulary_terms_after")})

    allergen_header, _, allergen_rows = csv_info(source_root / "phase5/allergens_all.csv")
    required_allergen_fields = {"example_id", "ingredient_text", "normalized_ingredient_text", "original_allergen_labels", "normalized_allergen_labels", "source_dataset", "source_row_id", "source_file_hash", "validation_status", "review_status"}
    if required_allergen_fields - set(allergen_header):
        issues.append({"code": "allergen_schema_missing_fields", "fields": sorted(required_allergen_fields-set(allergen_header))})
    allergen_ids = [r.get("example_id", "") for r in allergen_rows]
    if len(allergen_ids) != len(set(allergen_ids)) or any(not x for x in allergen_ids):
        issues.append({"code": "allergen_example_id_not_unique_or_missing"})
    missing_allergen_provenance = [r.get("example_id", "") for r in allergen_rows if any(not r.get(k, "").strip() for k in ("source_dataset", "source_row_id", "source_file_hash"))]
    if missing_allergen_provenance:
        issues.append({"code": "allergen_provenance_incomplete", "example_ids": missing_allergen_provenance[:20], "count": len(missing_allergen_provenance)})
    for row in allergen_rows:
        try:
            original_labels = json.loads(row.get("original_allergen_labels", ""))
            normalized_labels = json.loads(row.get("normalized_allergen_labels", ""))
            if not isinstance(original_labels, list) or not isinstance(normalized_labels, list):
                raise ValueError("label fields must be JSON arrays")
            if row.get("validation_status") == "accepted_unlabeled_unknown" and normalized_labels:
                issues.append({"code": "allergen_unknown_status_has_nonempty_labels", "example_id": row.get("example_id", "")})
            if not normalized_labels and row.get("validation_status") != "accepted_unlabeled_unknown":
                issues.append({"code": "empty_allergen_labels_not_marked_unknown", "example_id": row.get("example_id", "")})
        except (json.JSONDecodeError, ValueError) as exc:
            issues.append({"code": "allergen_label_schema_invalid", "example_id": row.get("example_id", ""), "reason": str(exc)})
            if len([i for i in issues if i["code"] == "allergen_label_schema_invalid"]) >= 20:
                break

    ambiguous_path = source_root / "phase7b/ambiguous_terms.csv"
    _, _, ambiguous_rows = csv_info(ambiguous_path)
    agar_rows = [r for r in ambiguous_rows if r.get("normalized_term", "").casefold() == "agar"]
    sample_header, _, sample_rows = csv_info(source_root / "phase7b/sample_recognition_results.csv")
    agar_sample = next((r for r in sample_rows if r.get("normalized_input_text", "").casefold() == "agar"), None)
    if not agar_rows or not agar_sample or agar_sample.get("match_status") != "ambiguous" or agar_sample.get("concept_id"):
        issues.append({"code": "agar_collision_not_preserved_as_ambiguous"})
    unresolved_sample = [r for r in sample_rows if r.get("match_status") == "unresolved"]
    if not unresolved_sample or any(r.get("concept_id") for r in unresolved_sample):
        issues.append({"code": "unknown_phrase_was_forced_into_class"})
    required_recognition_statuses = {"canonical_exact", "evidence_supported_exact", "provisional_exact", "synthetic_exact", "ambiguous", "unresolved"}
    missing_statuses = sorted(required_recognition_statuses - {r.get("match_status", "") for r in sample_rows})
    if missing_statuses:
        issues.append({"code": "recognition_case_coverage_missing", "statuses": missing_statuses})

    class_sets = {name.removesuffix(".csv"): {r.get("canonical_class_id", "") for r in csv_info(source_root / "phase4b_corrected" / name)[2]} for name in split_names}
    quality_report = json.loads((source_root / "final_reports/v4_quality_report.json").read_text(encoding="utf-8"))
    allergen_report = json.loads((source_root / "final_reports/v4_allergen_summary.json").read_text(encoding="utf-8"))
    phase5_report = json.loads((source_root / "phase5/allergen_quality_report.json").read_text(encoding="utf-8"))
    if len(all_rows) != quality_report.get("ingredient_dataset", {}).get("accepted_examples"):
        issues.append({"code": "baseline_count_does_not_reconcile_with_final_report"})
    if len(allergen_rows) != allergen_report.get("accepted_unique_examples"):
        issues.append({"code": "allergen_count_does_not_reconcile_with_final_report"})
    if len(allergen_rows) != phase5_report.get("accepted_unique_examples"):
        issues.append({"code": "allergen_count_does_not_reconcile_with_phase5_report"})
    metrics = {
        "baseline": {"examples": len(all_rows), "unique_phrases": len({r.get("normalized_text", "") for r in all_rows}), "canonical_classes": len(expected_canonical_ids), "classes_covered": len({r.get("canonical_class_id", "") for r in all_rows}), "split_counts": dict(Counter(r.get("split", "") for r in all_rows)), "classes_per_split": {k: len(v) for k, v in class_sets.items()}, "contributor_provenance_rows": len(provenance_rows), "known_group_leakage_groups": len(leaked)},
        "phase5_allergens": {"accepted_unique_examples": len(allergen_rows), "labels": len(json.loads((source_root / "phase5/allergen_quality_report.json").read_text(encoding="utf-8")).get("label_distribution", {})) if (source_root / "phase5/allergen_quality_report.json").exists() else None, "unknown_unlabeled_examples": sum(r.get("validation_status") == "accepted_unlabeled_unknown" for r in allergen_rows), "human_reviewed": 0},
        "phase7a": {"accepted_examples": len(accepted_rows), "source_derived": sum(r.get("source_type") == "source_derived" for r in accepted_rows), "synthetic": sum(r.get("source_type") == "synthetic" for r in accepted_rows), "canonical_classes": len(canonical_ids), "provisional_concepts": phase7a_report.get("provisional_concepts_added"), "human_reviewed": phase7a_report.get("human_reviewed_example_count", 0)},
        "consolidated_reports": {"baseline_accepted_examples": quality_report.get("ingredient_dataset", {}).get("accepted_examples"), "allergen_accepted_examples": allergen_report.get("accepted_unique_examples")},
        "issue_count": len(issues),
    }
    return {"passed": not issues, "issues": issues, "metrics": metrics}


def _docs(metrics: dict) -> dict[str, str]:
    b = metrics["baseline"]
    a = metrics["phase5_allergens"]
    v = metrics["phase7a"]
    splits = b["split_counts"]
    return {
        "DATASET_README.md": f"""# FoodLence V4 Final Dataset Package

This is the final handover package of existing FoodLence V4 data preparation artifacts. It does not create a new dataset or claim scientific ground truth. The included ingredient, allergen, vocabulary, recognition, and report components remain separate.

## Package inventory

- Baseline ingredient set: {b['examples']} unique normalized phrases, {b['canonical_classes']} stable canonical IDs. Split rows: train {splits.get('train',0)}, validation {splits.get('validation',0)}, test {splits.get('test',0)}. Original splits were copied without reassignment.
- Experimental vocabulary: {v['canonical_classes']} canonical entries and {v['provisional_concepts']} additional provisional concepts. See `vocabulary/expansion/expanded_vocabulary.csv` and evidence-tier reports.
- Automatically accepted Phase 7A examples: {v['accepted_examples']} rows ({v['source_derived']} source-derived; {v['synthetic']} synthetic). They are weak/provisional labels, not reviewed ground truth.
- Separate allergen component: {a['accepted_unique_examples']} unique examples with source labels; empty labels remain unknown.
- Recognition component: deterministic exact lookup examples and coverage reports. Ambiguity is preserved; unresolved input is never forced into a class.

## Provenance and evidence

Contributor-level records are included under `ingredients/ingredients_provenance.csv`. Phase 7A rows retain source file hashes, source row references, label methods, evidence tiers, synthetic flags, and `not_human_reviewed` status. Tier A means the recorded reference supports a particular identity relationship; it is not human review or broad ground-truth validation. Tier B is source-observed provisional terminology. Tier C is synthetic. Tier D is unresolved. The canonical taxonomy has 180 IDs, and its entries remain scientifically unverified.

No raw source files are included in this package. Source names, hashes, and row references stay in provenance fields. See `DATA_DICTIONARY.md`, `DATASET_LIMITATIONS.md`, `REPRODUCIBILITY.md`, `TASK02_FINAL_STATUS.md`, and `manifests/manifest.json`.
""",
        "DATA_DICTIONARY.md": """# Data Dictionary

## Baseline ingredients (`ingredients/`)

| Field | Meaning |
|---|---|
| `candidate_id` | Stable accepted-example identifier. |
| `ingredient_text` / `normalized_text` | Original phrase and deterministic normalized phrase. |
| `canonical_class_id` / `canonical_name` | One of the 180 existing FL IDs and its current label; scientific verification is not implied. |
| `source_type`, `source_contributions`, `contributor_provenance` | Aggregate provenance and contributor records, including source/synthetic overlap. |
| `is_synthetic`, `label_method`, `validation_status` | Generation and automatic validation metadata. |
| `review_status` | Human review state; accepted baseline rows are `not_human_reviewed`. |
| `split`, `split_group`, `semantic_form` | Existing split assignment and grouping keys. |
| `provenance_records` | Contributor IDs that link to the contributor-level provenance table. |

## Allergen rows (`allergens/`)

`example_id`, `ingredient_text`, `normalized_ingredient_text`, original and normalized multi-label arrays, source dataset/row/hash, `validation_status`, `validation_reason`, and `review_status` preserve the input label state. `accepted_unlabeled_unknown` means no label was supplied; it is not an allergen-free negative.

## Vocabulary (`vocabulary/`)

`class_id` or concept IDs identify canonical `FL-*` classes or provisional `PVA-*` / `PVB-*` concepts. `term` and `normalized_term` are vocabulary surfaces. `evidence_tier` describes evidence: A recorded identity support, B source-observed provisional phrase, C controlled synthetic surface, D unresolved. `review_status` and `taxonomy_verification_status` are independent of evidence tier.

## Recognition (`recognition/`)

`original_input_text`, `normalized_input_text`, `match_status`, matched term, concept ID/name, evidence tier, provenance, review status, ambiguity details, and verification limitation are returned for each sample. Status is categorical, not a calibrated probability.
""",
        "DATASET_LIMITATIONS.md": f"""# Dataset Limitations

- No documented human-reviewed ingredient examples are present. The required 3,000 reviewed examples are unmet.
- There are zero independently verified example labels. Some Tier A vocabulary relationships have a recorded authoritative reference, but that does not independently validate each example.
- The 180 canonical labels are structurally stable but scientifically unverified; 18,032 provisional concepts must not be presumed scientifically distinct.
- The baseline has {b['examples']} examples across 180 classes. Existing split coverage is train {b['classes_per_split'].get('ingredients_train',0)} classes, validation {b['classes_per_split'].get('ingredients_validation',0)}, and test {b['classes_per_split'].get('ingredients_test',0)}. This is too limited and uneven to establish reliable generalization.
- Product-level independence cannot be guaranteed because reliable product identifiers are unavailable. The package audit checks phrase, semantic-form, and split-group leakage only.
- Source-derived and synthetic rows are automatically processed; source and synthetic contributions can coexist in one deduplicated baseline example.
- Allergen labels are source-provided and unreviewed. {a['unknown_unlabeled_examples']} accepted examples have empty labels, treated as unknown, never as verified negatives. The ontology has {a['labels']} exact labels and does not establish medical suitability.
- Recognition uses exact lookup, not fuzzy matching. Ambiguous and unknown terms remain so. In-sample coverage is not accuracy; no independent reviewed benchmark exists for precision, recall, or F1.
""",
        "REPRODUCIBILITY.md": """# Reproducibility

The final package reuses existing outputs and does not rerun dataset generation. Each copied file is listed in `manifests/manifest.json` with package-relative path, component, schema version, row count when applicable, SHA-256, source artifact, data provenance, verification status, and human-review status. The manifest excludes its own checksum to avoid a circular digest.

The source builders and audit commands are maintained in the repository under `ml/data/`. For a fresh development run, follow `ml/data/README.md`; source datasets are local inputs and are not bundled here. The package manifest is deterministic for unchanged source files. File checksums allow recipients to detect changes. All paths in the manifest are relative; raw datasets are not copied.

Taxonomy validation command: `python ml/data/build_foodlence_v4.py --validate-taxonomy`. Phase 7B audit command: `python -m ml.data.v4.audit_expanded_vocabulary`. Recognition CLI help: `python ml/data/recognize_foodlence_ingredients.py --help`.
""",
        "TASK02_FINAL_STATUS.md": f"""# Task 02 Final Status

| Requirement | Status | Evidence / limitation |
|---|---|---|
| At least 3,000 human-reviewed ingredient/additive examples | **Not satisfied** | 0 documented human-reviewed examples. Automatic acceptance is not human-reviewed ground truth. |
| Approximately 150–200 ingredient classes | **Partially satisfied** | 180 stable IDs exist, but all current canonical classes remain scientifically unverified. |
| Separate allergen dataset | **Partially satisfied** | {a['accepted_unique_examples']} unique source-labeled examples are separate; labels are unreviewed and {a['unknown_unlabeled_examples']} records are unlabeled/unknown. |
| Reproducibility | **Partially satisfied** | Builders, deterministic audit outputs, provenance, and checksums exist; raw inputs are local and not packaged. |
| Provenance | **Satisfied structurally** | Baseline contributor records and Phase 7A source references are present and integrity-checked. This does not verify label truth. |
| Leakage-aware preparation | **Partially satisfied** | Existing group-aware splits pass known phrase/group checks; product-level independence is not verifiable without reliable product IDs. |
| Dataset quality reporting | **Satisfied structurally** | Phase 6A, 7A, and 7B reports and this manifest are included; reports do not replace independent review. |

**Overall: Task 02 is not fully satisfied.** Current packaged counts: {b['examples']} baseline ingredient examples; {v['accepted_examples']} automatic Phase 7A examples; {a['accepted_unique_examples']} separate allergen examples. Documented human-reviewed ingredient examples: 0. Independently verified example labels: 0. Tier A documentary support for selected terminology is not equivalent to independent example-level verification or human review.
""",
    }


def verify_package(package_dir: Path) -> dict:
    package_dir = Path(package_dir)
    issues = []
    manifest_path = package_dir / "manifests/manifest.json"
    if not manifest_path.is_file():
        return {"passed": False, "issues": ["manifest_missing"], "file_count": 0}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = {record["relative_file_path"] for record in manifest.get("files", [])}
    for record in manifest.get("files", []):
        path = package_dir / record["relative_file_path"]
        if not path.is_file():
            issues.append({"code": "manifest_file_missing", "path": record["relative_file_path"]})
            continue
        if sha256(path) != record.get("sha256"):
            issues.append({"code": "package_checksum_mismatch", "path": record["relative_file_path"]})
        if path.suffix.casefold() == ".csv":
            try:
                _, count, _ = csv_info(path)
                if count != record.get("row_count"):
                    issues.append({"code": "package_row_count_mismatch", "path": record["relative_file_path"], "actual": count, "manifest": record.get("row_count")})
            except (UnicodeDecodeError, csv.Error) as exc:
                issues.append({"code": "package_csv_invalid", "path": record["relative_file_path"], "reason": str(exc)})
    actual = {p.relative_to(package_dir).as_posix() for p in package_dir.rglob("*") if p.is_file()}
    expected = listed | {"manifests/manifest.json"}
    if actual != expected:
        issues.append({"code": "unmanifested_or_missing_package_files", "unmanifested": sorted(actual-expected), "missing": sorted(expected-actual)})
    return {"passed": not issues, "issues": issues, "file_count": len(actual), "manifested_data_file_count": len(listed)}


def build_package(source_root: Path = DEFAULT_ROOT, output_dir: Path | None = None) -> dict:
    source_root = Path(source_root)
    output_dir = Path(output_dir) if output_dir else source_root / PACKAGE_NAME
    audit = validate_source_artifacts(source_root)
    if not audit["passed"]:
        # Make failures reviewable without modifying source datasets.
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "manifests").mkdir(exist_ok=True)
        (output_dir / "manifests/integrity_failures.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return audit
    files = collect_files(source_root)
    docs = _docs(audit["metrics"])
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty final package: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for rel, source in sorted(files.items(), key=lambda x: x[0].as_posix()):
        target = output_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        header: list[str] = []
        rows = None
        row_count = None
        if target.suffix.casefold() == ".csv":
            header, row_count, rows = csv_info(target)
        source_rel = source.relative_to(source_root)
        records.append({
            "relative_file_path": rel.as_posix(),
            "dataset_component": _component(source_rel),
            "schema_version": _schema_version(target, header, rows),
            "row_count": row_count,
            "sha256": sha256(target),
            "data_provenance": _source_provenance(source_rel),
            "source_artifact_path": source_rel.as_posix(),
            "verification_status": _verification(source_rel),
            "human_review_status": _review_status(target, header, rows),
        })
    for filename, content in docs.items():
        (output_dir / filename).write_text(content, encoding="utf-8")
    for doc in sorted(output_dir.glob("*.md")):
        records.append({"relative_file_path": doc.name, "dataset_component": "documentation", "schema_version": "markdown-v1", "row_count": None, "sha256": sha256(doc), "data_provenance": "Generated handover documentation based on the audited local package inputs.", "source_artifact_path": "generated_by_package_final_dataset.py", "verification_status": "documentation_not_ground_truth", "human_review_status": "not_applicable"})
    manifest = {"package_version": PACKAGE_VERSION, "manifest_path": "manifests/manifest.json", "manifest_self_checksum": "excluded_to_avoid_circular_hash", "integrity_audit": audit, "files": sorted(records, key=lambda r: r["relative_file_path"])}
    manifest_dir = output_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package_integrity = verify_package(output_dir)
    audit["package_integrity"] = package_integrity
    audit["passed"] = audit["passed"] and package_integrity["passed"]
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output-dir", type=Path, help="defaults to <source-root>/final_package")
    args = parser.parse_args()
    result = build_package(args.source_root, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

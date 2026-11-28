import csv
import json
import subprocess
import sys
from pathlib import Path

from ml.data.v4.final_reports import build_reports
from ml.data.v4.taxonomy import TaxonomyClass


def _write(path: Path, rows, fields=None):
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root: Path):
    ingredients = root / "phase4b_corrected"
    allergens = root / "phase5"
    ingredients.mkdir(parents=True)
    allergens.mkdir(parents=True)
    classes = [
        TaxonomyClass("C-1", "alpha ingredient", "ingredient", "grain"),
        TaxonomyClass("C-2", "beta additive", "additive", "additive"),
    ]
    rows = [
        {"candidate_id": "ex-1", "normalized_text": "alpha", "canonical_class_id": "C-1", "canonical_name": "alpha ingredient", "semantic_form": "alpha", "parent_example_id": "tax:C-1", "review_status": "not_human_reviewed", "split": "train", "provenance_category": "both", "contributor_provenance": json.dumps([
            {"candidate_id": "src-1", "source_type": "source_derived", "review_status": "not_human_reviewed"},
            {"candidate_id": "syn-1", "source_type": "synthetic_taxonomy", "is_synthetic": True, "review_status": "not_human_reviewed"},
        ])},
        {"candidate_id": "ex-2", "normalized_text": "beta", "canonical_class_id": "C-2", "canonical_name": "beta additive", "semantic_form": "beta", "parent_example_id": "tax:C-2", "review_status": "not_human_reviewed", "split": "test", "provenance_category": "synthetic_only", "contributor_provenance": json.dumps([
            {"candidate_id": "syn-2", "source_type": "synthetic_taxonomy", "is_synthetic": True, "review_status": "not_human_reviewed"},
        ])},
    ]
    fields = list(rows[0])
    _write(ingredients / "ingredients_all.csv", rows, fields)
    _write(ingredients / "ingredients_train.csv", [rows[0]], fields)
    _write(ingredients / "ingredients_validation.csv", [], fields)
    _write(ingredients / "ingredients_test.csv", [rows[1]], fields)
    provenance = [
        {"candidate_id": "src-1", "source_type": "source_derived", "source_dataset": "fixture", "canonical_class_id": "C-1", "normalized_text": "alpha", "is_synthetic": "False", "review_status": "not_human_reviewed"},
        {"candidate_id": "syn-1", "source_type": "synthetic_taxonomy", "source_dataset": "fixture", "canonical_class_id": "C-1", "normalized_text": "alpha", "is_synthetic": "True", "review_status": "not_human_reviewed"},
        {"candidate_id": "syn-2", "source_type": "synthetic_taxonomy", "source_dataset": "fixture", "canonical_class_id": "C-2", "normalized_text": "beta", "is_synthetic": "True", "review_status": "not_human_reviewed"},
    ]
    _write(ingredients / "ingredients_provenance.csv", provenance)
    _write(ingredients / "conflicting_contributors.csv", [], ["candidate_id", "reason"])
    allergen = [{"example_id": "a-1", "normalized_allergen_labels": "[]", "duplicate_occurrences": "1", "review_status": "not_human_reviewed"}]
    _write(allergens / "allergens_all.csv", allergen)
    _write(allergens / "allergens_quarantined.csv", [], ["source_row_id", "source_text", "original_labels", "reason"])
    _write(allergens / "allergens_rejected.csv", [], ["source_row_id", "source_text", "reason"])
    (allergens / "allergen_quality_report.json").write_text(json.dumps({"source_rows_processed": 1, "source_file_hash": "fixture", "conflicting_duplicate_groups": 0}), encoding="utf-8")
    return ingredients, allergens, classes


def test_integrated_reports_reconcile_provenance_splits_and_separate_allergens(tmp_path):
    ingredient_dir, allergen_dir, taxonomy = _fixture(tmp_path)
    report = build_reports(ingredient_dir, allergen_dir, tmp_path / "reports", taxonomy)
    ingredient = report["ingredient_dataset"]
    assert ingredient["accepted_examples"] == 2
    assert ingredient["source_derived_contributor_occurrences"] == 1
    assert ingredient["synthetic_contributor_occurrences"] == 2
    assert ingredient["total_provenance_records"] == 3
    assert ingredient["source_only_examples"] == 0
    assert ingredient["synthetic_only_examples"] == 1
    assert ingredient["both_source_examples"] == 1
    assert ingredient["canonical_classes_covered"] == 2
    assert ingredient["split_integrity"]["all_examples_partitioned_once"]
    assert ingredient["split_integrity"]["invalid_canonical_class_examples"] == 0
    assert ingredient["ingredient_split_schemas_consistent"]
    assert ingredient["provenance_schema_complete"]
    assert not ingredient["split_integrity"]["normalized_phrase_leakage_groups"]
    assert not ingredient["split_integrity"]["semantic_form_leakage_groups"]
    assert not ingredient["split_integrity"]["parent_child_leakage_groups"]
    assert ingredient["human_reviewed_examples"] == 0
    allergen = report["allergen_dataset"]
    assert allergen["empty_label_occurrences_unknown"] == 1
    assert allergen["empty_labels_are_verified_negatives"] is False
    assert report["validation"]["allergen_source_count_reconciles"]
    output = tmp_path / "reports"
    expected = {"v4_quality_report.json", "v4_quality_report.md", "v4_class_distribution.csv", "v4_split_coverage.csv", "v4_provenance_summary.csv", "v4_allergen_summary.json", "v4_task02_gap_analysis.md"}
    assert expected <= {p.name for p in output.iterdir()}


def test_report_generation_is_deterministic(tmp_path):
    ingredients, allergens, taxonomy = _fixture(tmp_path)
    a, b = tmp_path / "reports-a", tmp_path / "reports-b"
    build_reports(ingredients, allergens, a, taxonomy)
    build_reports(ingredients, allergens, b, taxonomy)
    assert {p.name: p.read_bytes() for p in a.iterdir()} == {p.name: p.read_bytes() for p in b.iterdir()}


def test_v4_cli_help_and_taxonomy_validation():
    root = Path(__file__).resolve().parents[1]
    script = root / "ml" / "data" / "build_foodlence_v4.py"
    help_result = subprocess.run([sys.executable, str(script), "--help"], cwd=root, capture_output=True, text=True, check=False)
    taxonomy_result = subprocess.run([sys.executable, str(script), "--validate-taxonomy"], cwd=root, capture_output=True, text=True, check=False)
    assert help_result.returncode == 0
    assert "--generate-final-reports" in help_result.stdout
    assert taxonomy_result.returncode == 0
    assert json.loads(taxonomy_result.stdout)["structurally_valid"] is True

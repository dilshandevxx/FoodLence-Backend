import csv
import hashlib
import json
from pathlib import Path

from ml.data.v4.package_final_dataset import build_package, validate_source_artifacts
from ml.data.v4.taxonomy import TAXONOMY


def write_csv(path: Path, fields: list[str], rows: list[dict] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows or [])


def make_source_tree(root: Path):
    base_fields = ["candidate_id", "ingredient_text", "normalized_text", "canonical_class_id", "canonical_name", "source_type", "source_dataset", "source_reference", "source_row_id", "source_text", "parent_example_id", "generation_method", "is_synthetic", "label_method", "validation_method", "validation_status", "validation_reason", "review_status", "dataset_version", "semantic_form", "source_contributions", "provenance_records", "duplicate_occurrences", "split", "split_group", "contributor_provenance"]
    baseline = {"candidate_id":"base-1", "ingredient_text":"wheat flour", "normalized_text":"wheat flour", "canonical_class_id":"FL-001", "canonical_name":"wheat flour", "source_type":"source_derived", "source_dataset":"test.csv", "source_reference":"test.csv#1", "source_row_id":"1", "source_text":"wheat flour", "parent_example_id":"", "generation_method":"source", "is_synthetic":"False", "label_method":"exact", "validation_method":"test", "validation_status":"accepted", "validation_reason":"", "review_status":"not_human_reviewed", "dataset_version":"4.0.0", "semantic_form":"wheat flour", "source_contributions":"source_derived", "provenance_records":"prov-1", "duplicate_occurrences":"1", "split":"train", "split_group":"wheat flour", "contributor_provenance":"[]"}
    write_csv(root / "phase4b_corrected/ingredients_all.csv", base_fields, [baseline])
    for filename, split, rows in [("ingredients_train.csv", "train", [baseline]), ("ingredients_validation.csv", "validation", []), ("ingredients_test.csv", "test", [])]:
        write_csv(root / "phase4b_corrected" / filename, base_fields, rows)
    prov_fields = ["accepted_example_id", "candidate_id", "source_type", "source_dataset", "source_file_hash", "source_reference", "source_row_id", "ingredient_text", "source_text", "normalized_text", "canonical_class_id", "label_method", "generation_method", "is_synthetic", "validation_status", "validation_reason", "review_status"]
    write_csv(root / "phase4b_corrected/ingredients_provenance.csv", prov_fields, [{"accepted_example_id":"base-1", "candidate_id":"prov-1", "source_type":"source_derived", "source_dataset":"test.csv", "source_file_hash":"sha256:abc", "source_row_id":"1", "source_reference":"test.csv#1", "normalized_text":"wheat flour", "canonical_class_id":"FL-001", "review_status":"not_human_reviewed"}])
    write_csv(root / "phase4b_corrected/conflicting_contributors.csv", ["candidate_id"])
    write_csv(root / "phase4b_corrected/unmatched_contributors.csv", ["candidate_id"])

    allergen_fields = ["example_id", "ingredient_text", "normalized_ingredient_text", "original_allergen_labels", "normalized_allergen_labels", "source_dataset", "source_row_id", "source_file_hash", "label_method", "validation_status", "validation_reason", "review_status", "dataset_version", "provenance_records", "duplicate_occurrences"]
    allergen = {"example_id":"al-1", "ingredient_text":"plain flour", "normalized_ingredient_text":"plain flour", "original_allergen_labels":"[]", "normalized_allergen_labels":"[]", "source_dataset":"allergies.csv", "source_row_id":"3", "source_file_hash":"abc", "validation_status":"accepted_unlabeled_unknown", "review_status":"not_human_reviewed", "dataset_version":"5.0.0"}
    write_csv(root / "phase5/allergens_all.csv", allergen_fields, [allergen])
    write_csv(root / "phase5/allergens_quarantined.csv", allergen_fields)
    write_csv(root / "phase5/allergens_rejected.csv", allergen_fields)
    write_csv(root / "phase5/allergen_label_distribution.csv", ["label", "count"])
    (root / "phase5/allergen_quality_report.json").write_text(json.dumps({"label_distribution":{}, "empty_label_rows_unknown":1, "accepted_unique_examples":1}), encoding="utf-8")

    vocab_fields = ["vocabulary_id", "term", "normalized_term", "entry_kind", "class_id", "canonical_name", "taxonomy_type", "discovery_category", "evidence_tier", "relationship", "evidence_source_id", "evidence_url", "evidence_summary", "evidence_limitations", "taxonomy_verification_status", "review_status", "integration_status", "source_candidate_ids", "source_occurrence_count"]
    vocab = [{"vocabulary_id":c.class_id, "term":c.canonical_name, "normalized_term":c.canonical_name, "entry_kind":"canonical_class", "class_id":c.class_id, "canonical_name":c.canonical_name, "taxonomy_type":c.type, "review_status":"not_human_reviewed"} for c in TAXONOMY]
    vocab.append({"vocabulary_id":"PVB-11111111111111111111", "term":"purple yam", "normalized_term":"purple yam", "entry_kind":"source_observed_provisional_concept", "class_id":"PVB-11111111111111111111", "canonical_name":"purple yam", "evidence_tier":"B", "review_status":"not_human_reviewed"})
    write_csv(root / "phase7a/expanded_vocabulary.csv", vocab_fields, vocab)
    accepted_fields = ["example_id", "original_text", "normalized_text", "proposed_class_id", "proposed_class_name", "concept_namespace", "source_type", "source_dataset", "source_file_hash", "source_row_id", "source_text", "source_reference", "generation_method", "is_synthetic", "label_method", "evidence_tier", "validation_status", "review_status", "source_provenance"]
    accepted = {"example_id":"ex-1", "original_text":"purple yam", "normalized_text":"purple yam", "proposed_class_id":"PVB-11111111111111111111", "proposed_class_name":"purple yam", "concept_namespace":"PVB", "source_type":"source_derived", "source_dataset":"test.csv", "source_file_hash":"sha256:def", "source_row_id":"2", "source_reference":"test.csv#2", "is_synthetic":"False", "evidence_tier":"B", "validation_status":"accepted_automatic_provisional", "review_status":"not_human_reviewed"}
    write_csv(root / "phase7a/accepted_automatic_examples.csv", accepted_fields, [accepted])
    write_csv(root / "phase7a/candidate_examples.csv", accepted_fields, [accepted])
    write_csv(root / "phase7a/quarantined_examples.csv", accepted_fields + ["quarantine_reason"])
    write_csv(root / "phase7a/unresolved_candidates.csv", ["candidate_id", "candidate_phrase", "normalized_phrase", "review_status"])
    (root / "phase7a/vocabulary_expansion_report.json").write_text(json.dumps({"accepted_automatic_example_count":1, "accepted_source_derived_count":1, "accepted_synthetic_count":0, "vocabulary_terms_after":181, "provisional_concepts_added":1, "canonical_class_count_after":180, "human_reviewed_example_count":0}), encoding="utf-8")

    write_csv(root / "phase7b/ambiguous_terms.csv", ["normalized_term", "terms", "concept_ids", "entry_kinds"], [{"normalized_term":"agar", "concept_ids":"PVA-X|PVB-Y"}])
    sample_fields = ["original_input_text", "normalized_input_text", "match_status", "matched_vocabulary_term", "concept_id", "concept_name", "evidence_tier", "source_provenance", "review_status", "ambiguity_details", "verification_limitation"]
    sample_rows = [{"original_input_text":"agar", "normalized_input_text":"agar", "match_status":"ambiguous", "concept_id":"", "review_status":"not_human_reviewed"}, {"original_input_text":"mystery herb", "normalized_input_text":"mystery herb", "match_status":"unresolved", "concept_id":"", "review_status":"not_human_reviewed"}]
    sample_rows.extend({"original_input_text":status, "normalized_input_text":status, "match_status":status, "concept_id":"FL-001" if status == "canonical_exact" else "PVB-11111111111111111111", "review_status":"not_human_reviewed"} for status in ("canonical_exact", "evidence_supported_exact", "provisional_exact", "synthetic_exact"))
    write_csv(root / "phase7b/sample_recognition_results.csv", sample_fields, sample_rows)
    write_csv(root / "phase7b/concept_distribution.csv", ["concept_id"])
    (root / "phase7b/recognition_coverage_report.json").write_text("{}", encoding="utf-8")
    (root / "phase7b/recognition_coverage_report.md").write_text("Coverage", encoding="utf-8")
    (root / "phase7b/recognition_limitations.md").write_text("Limitations", encoding="utf-8")
    write_csv(root / "phase7b/possible_duplicate_concepts.csv", ["normalized_term"])

    for dirname in ("phase6b1", "phase6b2", "phase6b3", "phase6b4"):
        write_csv(root / dirname / "review_artifact.csv", ["review_status"])
    (root / "final_reports/v4_quality_report.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "final_reports/v4_quality_report.json").write_text(json.dumps({"ingredient_dataset":{"accepted_examples":1}}), encoding="utf-8")
    (root / "final_reports/v4_allergen_summary.json").write_text(json.dumps({"accepted_unique_examples":1}), encoding="utf-8")
    (root / "final_reports/v4_quality_report.md").write_text("Quality", encoding="utf-8")
    return root


def test_package_layout_manifest_checksums_and_reconciliation(tmp_path):
    source = make_source_tree(tmp_path / "source")
    output = tmp_path / "package"
    audit = build_package(source, output)
    assert audit["passed"]
    for folder in ("ingredients", "allergens", "vocabulary", "recognition", "reports", "manifests"):
        assert (output / folder).is_dir()
    manifest = json.loads((output / "manifests/manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity_audit"]["metrics"]["baseline"]["examples"] == 1
    assert manifest["integrity_audit"]["metrics"]["phase5_allergens"]["accepted_unique_examples"] == 1
    assert "manifests/manifest.json" not in {r["relative_file_path"] for r in manifest["files"]}
    for record in manifest["files"]:
        path = output / record["relative_file_path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_validation_preserves_provenance_review_and_separation(tmp_path):
    source = make_source_tree(tmp_path / "source")
    result = validate_source_artifacts(source)
    assert result["passed"], result["issues"]
    package = tmp_path / "package"
    build_package(source, package)
    provenance = list(csv.DictReader((package / "ingredients/ingredients_provenance.csv").open(encoding="utf-8")))
    assert provenance[0]["candidate_id"] == "prov-1"
    allergen = list(csv.DictReader((package / "allergens/allergens_all.csv").open(encoding="utf-8")))[0]
    assert allergen["normalized_allergen_labels"] == "[]"
    assert "ingredients/" not in str(package / "allergens").replace("\\", "/")
    sample = list(csv.DictReader((package / "recognition/sample_recognition_results.csv").open(encoding="utf-8")))
    agar = next(r for r in sample if r["normalized_input_text"] == "agar")
    assert agar["match_status"] == "ambiguous" and not agar["concept_id"]
    assert all(r["review_status"] == "not_human_reviewed" for r in sample)


def test_packaging_is_deterministic_for_unchanged_inputs(tmp_path):
    source = make_source_tree(tmp_path / "source")
    first, second = tmp_path / "package-a", tmp_path / "package-b"
    build_package(source, first)
    build_package(source, second)
    m1 = json.loads((first / "manifests/manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((second / "manifests/manifest.json").read_text(encoding="utf-8"))
    assert m1 == m2


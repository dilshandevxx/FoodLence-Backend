import csv
import hashlib
import json
from pathlib import Path

from ml.data.v4.expand_vocabulary import (
    build_taxonomy_index,
    expand_vocabulary,
    inspect_source_term,
    reconcile_example_conflicts,
    stable_id,
    validate_e_number,
    validate_mapping,
)
from ml.data.v4.taxonomy import TAXONOMY


ROOT = Path(__file__).parents[1]
DATA = ROOT / "ml/data/foodlence_generated_v4"


def test_provisional_namespaces_are_stable_and_separate():
    a = stable_id("PVA", "baking soda")
    b = stable_id("PVB", "baking soda")
    assert a == stable_id("PVA", "BAKING SODA")
    assert a != b
    assert a.startswith("PVA-") and b.startswith("PVB-")


def test_tier_a_tier_b_and_unsupported_synonym_assignment():
    owners, _ = build_taxonomy_index()
    a = inspect_source_term({"normalized_phrase": "baking soda", "discovery_category": "possible_new_ingredient"}, owners)
    assert a["tier"] == "A" and a["class_id"] == "FL-160"
    b = inspect_source_term({"normalized_phrase": "almond meal", "discovery_category": "possible_new_ingredient"}, owners)
    assert b["tier"] == "B" and b["class_id"].startswith("PVB-")
    bad = inspect_source_term({"normalized_phrase": "mono diglycerides", "discovery_category": "possible_additive"}, owners)
    assert bad["tier"] == "D"
    assert "omission" in bad["reason"]


def test_exact_canonical_mapping_and_alias_collision_handling():
    owners, _ = build_taxonomy_index()
    exact = inspect_source_term({"normalized_phrase": "citric acid", "discovery_category": "possible_additive"}, owners)
    assert exact["tier"] == "B" and exact["class_id"] == "FL-141"
    owners["same phrase"] = {"FL-001", "FL-002"}
    conflict = inspect_source_term({"normalized_phrase": "same phrase", "discovery_category": "possible_new_ingredient"}, owners)
    assert conflict["tier"] == "D"
    assert "conflicts" in conflict["reason"]


def test_e_number_requires_explicit_authoritative_mapping():
    assert validate_e_number("E 330", {}) == (False, "E-number-like term has no explicitly authoritative mapping")
    assert validate_e_number("E330", {"E330": "FL-141"}) == (True, "FL-141")
    owners, _ = build_taxonomy_index()
    unresolved = inspect_source_term({"normalized_phrase": "E999", "discovery_category": "possible_additive"}, owners)
    assert unresolved["tier"] == "D"
    exact = inspect_source_term({"normalized_phrase": "E330", "discovery_category": "possible_additive"}, owners, {"E330": "FL-141"})
    assert exact["tier"] == "A" and exact["class_id"] == "FL-141"


def test_invalid_class_references_and_provisional_tier_ids_are_rejected():
    canonical = {item.class_id for item in TAXONOMY}
    assert validate_mapping({"proposed_class_id": "FL-999", "evidence_tier": "B"}, canonical)
    assert validate_mapping({"proposed_class_id": "PVB-123", "evidence_tier": "B"}, canonical)
    assert validate_mapping({"proposed_class_id": stable_id("PVA", "x"), "evidence_tier": "B"}, canonical)
    assert validate_mapping({"proposed_class_id": stable_id("PVB", "x"), "evidence_tier": "B"}, canonical) == ""


def test_conflicting_normalized_labels_are_quarantined_together():
    rows = [
        {"example_id": "a", "normalized_text": "sodium bicarbonate", "proposed_class_id": "FL-160"},
        {"example_id": "b", "normalized_text": "sodium-bicarbonate", "proposed_class_id": "PVB-0123456789ABCDEF0123"},
        {"example_id": "c", "normalized_text": "agar", "proposed_class_id": "PVA-0123456789ABCDEF0123"},
    ]
    accepted, quarantined, count = reconcile_example_conflicts(rows)
    assert count == 1
    assert {r["example_id"] for r in quarantined} == {"a", "b"}
    assert [r["example_id"] for r in accepted] == ["c"]


def test_full_expansion_is_reproducible_and_preserves_baseline(tmp_path):
    baselines = [DATA / "phase4b_corrected" / name for name in ("ingredients_all.csv", "ingredients_train.csv", "ingredients_validation.csv", "ingredients_test.csv")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in baselines}
    reports = []
    for name in ("one", "two"):
        reports.append(expand_vocabulary(DATA / "phase2", DATA / "phase4b_corrected", DATA / "phase6b1",
                                         DATA / "phase6b2", DATA / "phase6b4", tmp_path / name))
    assert reports[0] == reports[1]
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in baselines} == before
    assert reports[0]["canonical_class_ids_unchanged"] is True
    assert reports[0]["unmatched_inventory_frequency_reconciles"] is True
    assert reports[0]["no_human_review_claims"] is True
    assert reports[0]["baseline_dataset_modified"] is False
    assert reports[0]["accepted_unique_semantic_forms"] <= reports[0]["accepted_unique_normalized_phrases"]
    for filename in ("expanded_vocabulary.csv", "candidate_examples.csv", "accepted_automatic_examples.csv",
                     "quarantined_examples.csv", "unresolved_candidates.csv", "evidence_tier_report.json",
                     "vocabulary_expansion_report.json", "vocabulary_expansion_report.md"):
        assert (tmp_path / "one" / filename).read_bytes() == (tmp_path / "two" / filename).read_bytes()
    accepted, _ = _read(tmp_path / "one/accepted_automatic_examples.csv")
    assert all(row["review_status"] == "not_human_reviewed" for row in accepted)


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream)), []

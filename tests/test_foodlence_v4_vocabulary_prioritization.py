import csv
import hashlib
import json
from pathlib import Path

import pytest

from ml.data.v4.prioritize_vocabulary import candidate_id, prioritize_vocabulary, score_candidate
from ml.data.v4.taxonomy import TAXONOMY


FIELDS = ["candidate_phrase", "normalized_phrase", "frequency", "source_references", "discovery_category", "suggested_existing_class_id", "suggested_existing_class_name", "suggested_new_class_name", "candidate_evidence", "evidence_source", "verification_status", "review_status", "priority_score", "priority_rationale", "character_count", "word_count", "pattern_flags"]


def _row(phrase, category, frequency=1):
    refs = [{"candidate_id": f"src-{phrase}", "source_dataset": "fixture.csv", "source_file_hash": "abc", "source_row_id": "4", "source_text": phrase}]
    return {"candidate_phrase": phrase, "normalized_phrase": phrase, "frequency": str(frequency), "source_references": json.dumps(refs), "discovery_category": category, "suggested_existing_class_id": "", "suggested_existing_class_name": "", "suggested_new_class_name": phrase, "candidate_evidence": "heuristic only", "evidence_source": "fixture.csv row 4", "verification_status": "unverified", "review_status": "not_human_reviewed", "priority_score": "50", "priority_rationale": "fixture", "character_count": str(len(phrase)), "word_count": str(len(phrase.split())), "pattern_flags": ""}


def _write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_candidate_ids_scoring_and_ranking_are_stable():
    assert candidate_id("agar agar") == candidate_id("agar agar")
    assert candidate_id("agar agar") != candidate_id("agar")
    row = _row("agar agar", "possible_new_ingredient", 5)
    score1 = score_candidate(row, {"status": "evidence_found"}, set(), {})
    score2 = score_candidate(row, {"status": "evidence_found"}, set(), {})
    assert score1 == score2
    assert 0 <= score1[0] <= 100
    assert score1[1]["authoritative_evidence"] == 25


def test_shortlist_category_caps_diversity_and_reconciliation(tmp_path):
    source = tmp_path / "candidates.csv"
    rows = [
        _row("baking soda", "possible_new_ingredient", 3),
        _row("agar agar", "possible_new_ingredient", 5),
        _row("food starch modified", "possible_new_ingredient", 7),
        _row("citric acid", "possible_additive", 10),
        _row("water and oil", "compound_ingredient_expression", 100),
        _row("unclear phrase (variant)", "ambiguous", 100),
        _row("cornstarch modified", "possible_new_ingredient", 2),
        _row("corn starch modified", "possible_new_ingredient", 2),
    ]
    _write(source, rows)
    report = prioritize_vocabulary(source, tmp_path / "out", limit=5)
    shortlist = _read(tmp_path / "out" / "priority_shortlist.csv")
    deferred = _read(tmp_path / "out" / "deferred_candidates.csv")
    assert len(shortlist) <= 5
    assert len(shortlist) + len(deferred) == len(rows)
    assert report["shortlist_and_deferred_reconcile"]
    allocation = report["selected_allocation_counts"]
    assert allocation["standalone_food_candidates"] <= 300
    assert allocation["additive_candidates"] <= 150
    assert allocation["compound_investigation_candidates"] + allocation["ambiguous_or_existing_class_candidates"] <= 50
    assert len({x["candidate_id"] for x in shortlist}) == len(shortlist)
    assert all(x["integration_status"] == "not_integrated" for x in shortlist)
    assert any(x["normalized_phrase"] == "baking soda" and x["proposed_existing_class_id"] == "FL-160" for x in shortlist)
    assert len(_read(tmp_path / "out" / "compound_investigation_queue.csv")) <= len(shortlist)
    # Canonically distinct compounds are not assigned class IDs automatically.
    for row in shortlist:
        if row["discovery_category"] == "compound_ingredient_expression":
            assert not row["proposed_existing_class_id"]
    selected_phrases = {x["normalized_phrase"] for x in shortlist}
    assert not {"cornstarch modified", "corn starch modified"}.issubset(selected_phrases)


def test_evidence_and_review_fields_are_truthful_and_preserved(tmp_path):
    source = tmp_path / "candidates.csv"
    rows = [_row("agar agar", "possible_new_ingredient", 8), _row("baking soda", "possible_new_ingredient", 7), _row("mono and diglycerides", "compound_ingredient_expression", 7), _row("unknown botanical", "possible_new_ingredient", 6)]
    _write(source, rows)
    out = tmp_path / "out"
    report = prioritize_vocabulary(source, out, limit=10)
    registry = _read(out / "candidate_evidence_registry.csv")
    by_phrase = {row["normalized_phrase"]: row for row in registry}
    assert by_phrase["agar agar"]["evidence_status"] == "evidence_found"
    assert "hfpappexternal.fda.gov" in by_phrase["agar agar"]["evidence_url"]
    assert json.loads(by_phrase["agar agar"]["original_source_references"])[0]["source_row_id"] == "4"
    assert by_phrase["unknown botanical"]["evidence_status"] == "not_checked"
    assert by_phrase["mono and diglycerides"]["evidence_status"] == "evidence_found"
    assert not by_phrase["unknown botanical"]["evidence_url"]
    template = _read(out / "human_review_template.csv")
    assert all(row["review_status"] == "pending_human_review" for row in template)
    assert all(not row["reviewer_decision"] and not row["reviewer_identifier"] and not row["review_timestamp"] and not row["review_justification"] for row in template)
    assert report["human_review_completed_count"] == 0
    assert report["all_proposals_non_activating"]
    assert not any(row["integration_status"] == "integrated" for row in registry)


def test_output_is_reproducible_and_taxonomy_is_unchanged(tmp_path):
    source = tmp_path / "candidates.csv"
    _write(source, [_row("baking soda", "possible_new_ingredient", 2), _row("citric acid", "possible_additive", 3)])
    tax_before = hashlib.sha256(repr(TAXONOMY).encode()).hexdigest()
    a, b = tmp_path / "a", tmp_path / "b"
    prioritize_vocabulary(source, a, limit=20)
    prioritize_vocabulary(source, b, limit=20)
    tax_after = hashlib.sha256(repr(TAXONOMY).encode()).hexdigest()
    assert tax_before == tax_after
    assert {p.name: p.read_bytes() for p in a.iterdir()} == {p.name: p.read_bytes() for p in b.iterdir()}


def test_empty_inventory_and_invalid_inputs(tmp_path):
    source = tmp_path / "empty.csv"
    _write(source, [])
    report = prioritize_vocabulary(source, tmp_path / "empty-out")
    assert report["discovery_inventory_rows"] == 0
    assert report["shortlist_count"] == 0
    assert report["deferred_count"] == 0
    bad = tmp_path / "bad.csv"
    bad.write_text("candidate_phrase,normalized_phrase\na,b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        prioritize_vocabulary(bad, tmp_path / "bad-out")
    with pytest.raises(ValueError, match="non-negative"):
        prioritize_vocabulary(source, tmp_path / "negative-out", limit=-1)

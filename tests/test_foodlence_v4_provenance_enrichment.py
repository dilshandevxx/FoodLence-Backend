import json

from ml.data.v4.enrich_provenance import enrich


def test_enrichment_preserves_every_contributor_and_split():
    source = [{
        "candidate_id": "src-1", "ingredient_text": "Oil", "normalized_text": "oil",
        "canonical_class_id": "FL-1", "source_dataset": "off", "source_row_id": "r1",
        "source_file_hash": "abc", "label_method": "taxonomy_exact",
        "validation_status": "matched_provisional", "review_status": "not_human_reviewed",
        "is_synthetic": "false",
    }]
    synthetic = [{
        "candidate_id": "syn-1", "ingredient_text": "Oil", "normalized_text": "oil",
        "canonical_class_id": "FL-1", "source_type": "synthetic_taxonomy",
        "source_dataset": "taxonomy", "source_reference": "FL-1",
        "generation_method": "controlled", "is_synthetic": "True",
        "validation_status": "accepted", "review_status": "not_human_reviewed",
    }]
    accepted = [{"candidate_id": "ex-1", "normalized_text": "oil", "canonical_class_id": "FL-1", "split": "train"}]
    enriched, unmatched, conflicts = enrich(source, synthetic, accepted, accepted)
    assert not unmatched and not conflicts
    row = enriched[0]
    assert row["provenance_category"] == "both"
    provenance = json.loads(row["contributor_provenance"])
    assert [p["candidate_id"] for p in provenance] == ["src-1", "syn-1"]
    assert provenance[0]["validation_status"] == "matched_provisional"
    assert provenance[0]["review_status"] == "not_human_reviewed"
    assert provenance[1]["is_synthetic"] is True
    assert row["split"] == "train"


def test_conflicting_class_and_unmatched_contributors_are_separated():
    accepted = [{"candidate_id": "ex-1", "normalized_text": "oil", "canonical_class_id": "FL-1", "split": "train"}]
    source = [
        {"candidate_id": "bad-label", "normalized_text": "oil", "canonical_class_id": "FL-2"},
        {"candidate_id": "missing", "normalized_text": "salt", "canonical_class_id": "FL-3"},
    ]
    enriched, unmatched, conflicts = enrich(source, [], accepted, accepted)
    assert conflicts == [{"candidate_id": "bad-label", "reason": "canonical mismatch"}]
    assert unmatched == [{"candidate_id": "missing", "reason": "no accepted phrase match"}]
    assert not json.loads(enriched[0]["contributor_provenance"])


def test_deterministic_provenance_serialization():
    source = [{"candidate_id": "b", "normalized_text": "oil", "canonical_class_id": "FL-1"},
              {"candidate_id": "a", "normalized_text": "oil", "canonical_class_id": "FL-1"}]
    accepted = [{"candidate_id": "ex", "normalized_text": "oil", "canonical_class_id": "FL-1", "split": "train"}]
    first = enrich(source, [], accepted, accepted)[0]
    second = enrich(list(reversed(source)), [], accepted, accepted)[0]
    assert first == second

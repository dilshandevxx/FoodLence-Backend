from ml.data.v4.generate_variants import generate_candidates
from ml.data.v4.taxonomy import TaxonomyClass, TAXONOMY
from ml.data.v4.validate import validate_generated


def test_generation_is_deterministic_and_provenance_complete():
    first = generate_candidates(TAXONOMY)
    assert first == generate_candidates(TAXONOMY)
    assert all(row["is_synthetic"] and row["review_status"] == "not_human_reviewed" for row in first)
    assert validate_generated(first, TAXONOMY)["structurally_valid"]


def test_generation_inherits_parent_and_marks_surface_noise():
    rows = generate_candidates([TaxonomyClass("T1","citric acid","additive","acid",("citric acid anhydrous",))])
    assert all(row["canonical_class_id"] == "T1" for row in rows)
    assert all(row["parent_example_id"] == "taxonomy:T1" for row in rows)
    assert any(row["generation_method"] == "case_format" for row in rows)


def test_conflicting_label_and_review_claim_fail_validation():
    rows = generate_candidates([TaxonomyClass("T1","citric acid","additive","acid"),TaxonomyClass("T2","citric acid","additive","acid")])
    result = validate_generated(rows)
    assert not result["structurally_valid"]
    assert result["conflicting_normalized_phrases"]
    rows[0]["review_status"] = "human_reviewed"
    assert any(issue["code"] == "unsupported_review_claim" for issue in validate_generated(rows)["issues"])

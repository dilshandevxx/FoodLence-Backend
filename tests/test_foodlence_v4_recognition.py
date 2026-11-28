import csv
import json
from ml.data.v4.recognize_ingredients import IngredientRecognizer, normalize_lookup, read_phrases_csv


def make_recognizer(tmp_path):
    vocab = tmp_path / "vocab.csv"
    fields = ["term", "normalized_term", "entry_kind", "class_id", "canonical_name", "evidence_tier", "review_status"]
    data = [
        {"term":"Wheat Flour", "normalized_term":"wheat flour", "entry_kind":"canonical_class", "class_id":"FL-001", "canonical_name":"wheat flour", "evidence_tier":"", "review_status":"not_human_reviewed"},
        {"term":"purple yam powder", "normalized_term":"purple yam powder", "entry_kind":"provisional_term", "class_id":"PVB-11111111111111111111", "canonical_name":"purple yam powder", "evidence_tier":"B", "review_status":"not_human_reviewed"},
        {"term":"E 202", "normalized_term":"e 202", "entry_kind":"provisional_term", "class_id":"PVB-22222222222222222222", "canonical_name":"E 202", "evidence_tier":"B", "review_status":"not_human_reviewed"},
        {"term":"same term", "normalized_term":"same term", "entry_kind":"provisional_term", "class_id":"PVB-33333333333333333333", "canonical_name":"first", "evidence_tier":"B", "review_status":"not_human_reviewed"},
        {"term":"same term", "normalized_term":"same term", "entry_kind":"provisional_term", "class_id":"PVB-44444444444444444444", "canonical_name":"second", "evidence_tier":"B", "review_status":"not_human_reviewed"},
    ]
    with vocab.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(data)
    examples = tmp_path / "examples.csv"
    fields2 = ["normalized_text", "original_text", "example_id", "source_dataset", "source_row_id", "source_reference", "source_type", "is_synthetic", "proposed_class_id", "proposed_class_name", "evidence_tier", "review_status"]
    with examples.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields2); w.writeheader(); w.writerow(dict(normalized_text="purple yam powder", original_text="purple yam powder", example_id="x1", source_dataset="local.csv", source_row_id="4", source_reference="local.csv#4", source_type="source_derived", is_synthetic="False", proposed_class_id="PVB-11111111111111111111", proposed_class_name="purple yam powder", evidence_tier="B", review_status="not_human_reviewed")); w.writerow(dict(normalized_text="wheat-bran", original_text="wheat-bran", example_id="s1", source_dataset="synthetic", source_row_id="", source_reference="parent", source_type="synthetic", is_synthetic="True", proposed_class_id="FL-002", proposed_class_name="wheat bran", evidence_tier="C", review_status="not_human_reviewed"))
    return IngredientRecognizer(vocab, examples)


def test_unicode_case_whitespace_punctuation_normalization():
    assert normalize_lookup("  WHEAT\u00a0FLOUR! ") == "wheat flour"
    assert normalize_lookup("caf" + chr(0xE9)) == "caf" + chr(0xE9)
    assert normalize_lookup("ingredient" + chr(0x2013) + "name") == "ingredient-name"


def test_canonical_provisional_and_review_status(tmp_path):
    r = make_recognizer(tmp_path)
    a = r.recognize("WHEAT FLOUR")
    b = r.recognize("purple yam powder")
    assert a["match_status"] == "canonical_exact" and a["concept_id"] == "FL-001"
    assert b["match_status"] == "provisional_exact" and b["evidence_tier"] == "B"
    assert b["review_status"] == "not_human_reviewed"


def test_ambiguity_unknown_and_e_number_are_conservative(tmp_path):
    r = make_recognizer(tmp_path)
    assert r.recognize("same term")["match_status"] == "ambiguous"
    assert r.recognize("E 202")["match_status"] == "provisional_exact"
    out = r.recognize("uncertain turmeric-like root")
    assert out["match_status"] == "unresolved" and not out["concept_id"]
    assert r.recognize("")["match_status"] == "unresolved"
    assert r.recognize("E-999999")["match_status"] == "unresolved"


def test_synthetic_surface_gets_explicit_synthetic_status(tmp_path):
    assert make_recognizer(tmp_path).recognize("wheat-bran")["match_status"] == "synthetic_exact"


def test_provenance_and_reproducibility(tmp_path):
    r = make_recognizer(tmp_path)
    x = r.recognize("purple yam powder")
    assert x == r.recognize("purple yam powder")
    assert x["source_provenance"][0]["source_row_id"] == "4"
    assert x["review_status"] == "not_human_reviewed"


def test_batch_csv_reading(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text("phrase\nWheat Flour\n", encoding="utf-8")
    assert read_phrases_csv(p) == ["Wheat Flour"]


def test_malformed_csv_and_result_schema(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("other\nfoo\n", encoding="utf-8")
    try:
        read_phrases_csv(bad)
    except ValueError as exc:
        assert "requires a phrase column" in str(exc)
    else:
        raise AssertionError("malformed CSV must be rejected")
    result = make_recognizer(tmp_path).recognize("wheat flour")
    required = {"original_input_text", "normalized_input_text", "match_status", "matched_vocabulary_term", "concept_id", "concept_name", "evidence_tier", "source_provenance", "review_status", "ambiguity_details", "verification_limitation"}
    assert required <= set(result)


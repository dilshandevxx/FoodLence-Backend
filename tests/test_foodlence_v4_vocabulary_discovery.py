import csv
import json
from pathlib import Path

import pytest

from ml.data.v4.discover_vocabulary import discover_vocabulary, normalize_candidate
from ml.data.v4.taxonomy import TaxonomyClass


FIELDS = ["candidate_id", "ingredient_text", "normalized_text", "source_dataset", "source_file_hash", "source_row_id", "source_text", "validation_status"]


def _write_input(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(cid, phrase, row_id):
    return {"candidate_id": cid, "ingredient_text": phrase, "normalized_text": phrase, "source_dataset": "fixture.csv", "source_file_hash": "sha256-fixture", "source_row_id": str(row_id), "source_text": f"source:{phrase}", "validation_status": "unmatched"}


def test_normalization_is_deterministic_and_unicode_safe():
    assert normalize_candidate("  ＳＥＥＤ—OIL\t") == "seed oil"
    assert normalize_candidate("  ＳＥＥＤ—OIL\t") == normalize_candidate("seed oil")


def test_frequency_categories_provenance_and_no_automatic_mapping(tmp_path):
    source = tmp_path / "unmatched.csv"
    _write_input(source, [
        _row("c1", "olive leaf extract", 11), _row("c2", "olive leaf extract", 12),
        _row("c3", "water, sugar and cocoa", 13), _row("c4", "E 999", 14),
        _row("c5", "vitamin b (niacin)", 15), _row("c6", "https://bad.example", 16),
        _row("c7", "alias phrase", 17),
    ])
    taxonomy = (TaxonomyClass("T-1", "vanillin", "ingredient", "flavor", aliases=("alias phrase",)),)
    report = discover_vocabulary(source, tmp_path / "out", taxonomy)
    with (tmp_path / "out" / "vocabulary_candidates.csv").open(encoding="utf-8", newline="") as stream:
        rows = {row["normalized_phrase"]: row for row in csv.DictReader(stream)}
    assert report["source_occurrences_analyzed"] == 7
    assert report["unique_normalized_candidate_phrases"] == 6
    assert report["input_output_occurrence_counts_reconcile"]
    assert rows["olive leaf extract"]["frequency"] == "2"
    refs = json.loads(rows["olive leaf extract"]["source_references"])
    assert {ref["source_row_id"] for ref in refs} == {"11", "12"}
    assert rows["water, sugar and cocoa"]["discovery_category"] == "compound_ingredient_expression"
    assert rows["e 999"]["discovery_category"] == "possible_additive"
    assert not rows["e 999"]["suggested_new_class_name"]
    assert rows["vitamin b (niacin)"]["discovery_category"] == "ambiguous"
    assert rows["https://bad.example"]["discovery_category"] == "invalid_or_noise"
    assert rows["alias phrase"]["discovery_category"] == "possible_existing_class_alias"
    assert rows["alias phrase"]["suggested_existing_class_id"] == "T-1"
    assert not rows["olive leaf extract"]["suggested_existing_class_id"]
    assert all(r["verification_status"] == "unverified" and r["review_status"] == "not_human_reviewed" for r in rows.values())
    assert report["taxonomy_modified"] is False


def test_empty_input_and_reproducible_outputs(tmp_path):
    empty = tmp_path / "empty.csv"
    _write_input(empty, [])
    first, second = tmp_path / "out-a", tmp_path / "out-b"
    report = discover_vocabulary(empty, first)
    discover_vocabulary(empty, second)
    assert report["source_occurrences_analyzed"] == 0
    assert report["unique_normalized_candidate_phrases"] == 0
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {p.name: p.read_bytes() for p in second.iterdir()}
    assert len(list(csv.DictReader((first / "vocabulary_candidates.csv").open(encoding="utf-8", newline="")))) == 0


def test_malformed_schema_is_rejected_without_creating_output(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("candidate_id,ingredient_text\na,b\n", encoding="utf-8")
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="missing required columns"):
        discover_vocabulary(source, output)
    assert not output.exists()


def test_malformed_occurrence_is_retained_and_flagged(tmp_path):
    source = tmp_path / "extra-fields.csv"
    source.write_text(
        ",".join(FIELDS) + "\n" + "id,text,text,fixture.csv,hash,42,original,unmatched,unexpected\n",
        encoding="utf-8",
    )
    report = discover_vocabulary(source, tmp_path / "out")
    assert report["source_occurrences_analyzed"] == 1
    assert report["malformed_source_occurrences_retained"] == 1
    with (tmp_path / "out" / "vocabulary_candidates.csv").open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["frequency"] == "1"
    assert row["discovery_category"] == "invalid_or_noise"
    assert "unexpected" in row["source_references"]

import csv

from ml.data.v4.extract_sources import extract_sources, match_candidate, normalize
from ml.data.v4.taxonomy import TaxonomyClass


def classes():
    return (TaxonomyClass("T1", "citric acid", "additive", "acid", ("citric-acid",)),
            TaxonomyClass("T2", "milk powder", "ingredient", "dairy"))


def test_normalize_unicode_and_exact_alias():
    assert normalize("  CITRIC\u00a0ACID ") == "citric acid"
    assert match_candidate("citric-acid", *(__import__("ml.data.v4.extract_sources", fromlist=["taxonomy_index"]).taxonomy_index(classes()))) ["validation_status"] == "matched_provisional"


def test_unmatched_and_ambiguous_alias():
    mod = __import__("ml.data.v4.extract_sources", fromlist=["taxonomy_index"])
    index, ids = mod.taxonomy_index(classes())
    assert match_candidate("mystery", index, ids)["validation_status"] == "unmatched"
    ambiguous = classes() + (TaxonomyClass("T3", "sodium citrate", "additive", "salt", ("shared",)), TaxonomyClass("T4", "potassium citrate", "additive", "salt", ("shared",)))
    index, ids = mod.taxonomy_index(ambiguous)
    assert match_candidate("shared", index, ids)["validation_status"] == "ambiguous"


def test_extract_provenance_composites_duplicates_and_stable_ids(tmp_path):
    source = tmp_path / "input.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["ingredient"])
        writer.writeheader()
        writer.writerows([{"ingredient":"Citric Acid"}, {"ingredient":"citric acid"}, {"ingredient":"milk powder, sugar"}, {"ingredient":""}])
    out1, out2 = tmp_path / "out1", tmp_path / "out2"
    r1 = extract_sources(source, out1, classes())
    r2 = extract_sources(source, out2, classes())
    assert r1 == r2
    with (out1 / "source_candidates.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert all(row["review_status"] == "not_human_reviewed" and row["is_synthetic"] == "false" for row in rows)
    assert rows[0]["source_file_hash"] and rows[0]["source_row_id"]
    assert rows[0]["candidate_id"] == list(csv.DictReader((out2 / "source_candidates.csv").open(encoding="utf-8", newline="")))[0]["candidate_id"]
    assert r1["repeated_occurrences"] == 1
    assert r1["rows_skipped_compound_or_empty"] == 2

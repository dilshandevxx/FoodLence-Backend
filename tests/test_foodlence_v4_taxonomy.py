from dataclasses import replace

from ml.data.v4.taxonomy import TAXONOMY, TaxonomyClass
from ml.data.v4.validate import validate_taxonomy


def sample(**changes):
    base = TaxonomyClass("T-001", "citric acid", "additive", "acidity_regulator", ("e330",), "E330", "acidulant")
    return replace(base, **changes)


def test_bundled_taxonomy_is_reproducible_and_structurally_valid():
    assert TAXONOMY == tuple(TAXONOMY)
    result = validate_taxonomy(TAXONOMY)
    assert result["structurally_valid"]
    assert 180 <= result["class_count"] <= 200


def test_duplicate_class_id_and_name_are_reported():
    result = validate_taxonomy([sample(), sample(canonical_name="citric acid")])
    codes = {issue["code"] for issue in result["issues"]}
    assert {"duplicate_class_id", "duplicate_canonical_name"} <= codes


def test_alias_conflicts_are_reported():
    result = validate_taxonomy([sample(), sample(class_id="T-002", canonical_name="sodium citrate", aliases=("e330",), e_number="")])
    assert any(issue["code"] == "conflicting_alias" for issue in result["issues"])


def test_invalid_e_number_and_type_are_reported():
    result = validate_taxonomy([sample(e_number="E33X", type="chemical")])
    codes = {issue["code"] for issue in result["issues"]}
    assert {"invalid_e_number_format", "invalid_type"} <= codes


def test_missing_provenance_is_reported():
    result = validate_taxonomy([sample(taxonomy_source="")])
    assert any(issue["code"] == "missing_required_field" for issue in result["issues"])

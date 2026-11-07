import pytest
from app.knowledge_base.allergen_engine import allergen_engine, CORE_ALLERGEN_TAXONOMY, KNOWN_ADDITIVES


def test_core_allergen_taxonomy_structure():
    """
    Validates presence of essential FDA Big 9 + EU 14 allergens in the built-in taxonomy.
    """
    required_allergens = [
        "peanut",
        "tree_nuts",
        "milk",
        "egg",
        "gluten",
        "soy",
        "fish",
        "shellfish",
        "sesame",
        "sulfites",
        "mustard",
        "celery",
    ]
    for allergen_code in required_allergens:
        assert allergen_code in CORE_ALLERGEN_TAXONOMY
        data = CORE_ALLERGEN_TAXONOMY[allergen_code]
        assert "name" in data
        assert "synonyms" in data
        assert len(data["synonyms"]) > 0
        assert data["default_severity"] in ("mild", "moderate", "severe")


def test_match_allergens_direct_and_synonyms():
    """
    Tests direct and synonym matching for allergens.
    """
    ingredients = [
        "organic roasted peanuts",
        "pasteurized whole milk",
        "casein",
        "ovalbumin",
        "durum wheat semolina",
        "edamame beans",
        "smoked salmon",
        "tiger prawn",
        "toasted sesame oil",
    ]
    matches = allergen_engine.match_allergens_for_ingredients(ingredients)
    matched_codes = {m["allergen_code"] for m in matches}

    assert "peanut" in matched_codes
    assert "milk" in matched_codes
    assert "egg" in matched_codes
    assert "gluten" in matched_codes
    assert "soy" in matched_codes
    assert "fish" in matched_codes
    assert "shellfish" in matched_codes
    assert "sesame" in matched_codes


def test_match_additives_known_and_unknown():
    """
    Tests additive retrieval for both recognized and unrecognized E-numbers.
    """
    codes = ["E102", "E330", "E621", "E9999"]
    additives = allergen_engine.match_additives(codes)

    found_codes = {a["e_number"] for a in additives}
    assert "E102" in found_codes
    assert "E330" in found_codes
    assert "E621" in found_codes
    assert "E9999" not in found_codes

    tartrazine = next(a for a in additives if a["e_number"] == "E102")
    assert tartrazine["name"] == "Tartrazine"
    assert tartrazine["risk_level"] == "caution"

    citric_acid = next(a for a in additives if a["e_number"] == "E330")
    assert citric_acid["name"] == "Citric Acid"
    assert citric_acid["risk_level"] == "safe"


def test_evaluate_safety_verdict_severe_conflict():
    """
    A profile containing peanut allergy must yield UNSAFE / red when peanut is present.
    """
    matched = [
        {
            "allergen_code": "peanut",
            "allergen_name": "Peanuts",
            "severity_default": "severe",
            "cross_reactivity": "direct",
            "matched_ingredient": "peanuts",
        }
    ]
    user_profile_allergens = [
        {"allergen_code": "peanut", "name": "Peanuts", "severity": "severe"}
    ]

    verdict, color, summary, evaluated = allergen_engine.evaluate_safety_verdict(
        matched_allergens=matched,
        detected_additives=[],
        profile_allergens=user_profile_allergens,
        profile_name="Dilshan",
    )

    assert verdict == "UNSAFE"
    assert color == "red"
    assert "DANGER" in summary
    assert "Peanuts" in summary
    assert evaluated[0]["is_profile_conflict"] is True


def test_evaluate_safety_verdict_mild_caution():
    """
    A mild or moderate conflict must yield CAUTION / yellow.
    """
    matched = [
        {
            "allergen_code": "soy",
            "allergen_name": "Soy & Soybeans",
            "severity_default": "moderate",
            "cross_reactivity": "direct",
            "matched_ingredient": "soy lecithin",
        }
    ]
    user_profile_allergens = [
        {"allergen_code": "soy", "name": "Soy", "severity": "moderate"}
    ]

    verdict, color, summary, evaluated = allergen_engine.evaluate_safety_verdict(
        matched_allergens=matched,
        detected_additives=[],
        profile_allergens=user_profile_allergens,
        profile_name="Family Profile",
    )

    assert verdict == "CAUTION"
    assert color == "yellow"
    assert "WARNING" in summary
    assert evaluated[0]["is_profile_conflict"] is True


def test_evaluate_safety_verdict_additive_caution_only():
    """
    When no allergen conflicts exist but hazardous/caution additives are detected,
    verdict should flag CAUTION / yellow.
    """
    additives = [
        {
            "e_number": "E102",
            "name": "Tartrazine",
            "category": "Color",
            "risk_level": "caution",
            "explanation": "Azo dye",
            "health_concerns": None,
        }
    ]

    verdict, color, summary, _ = allergen_engine.evaluate_safety_verdict(
        matched_allergens=[],
        detected_additives=additives,
        profile_allergens=[],
        profile_name="Clean Eater",
    )

    assert verdict == "CAUTION"
    assert color == "yellow"
    assert "Tartrazine" in summary


def test_evaluate_safety_verdict_clean_safe():
    """
    Completely clean ingredients without conflicts or dangerous additives should return SAFE / green.
    """
    verdict, color, summary, evaluated = allergen_engine.evaluate_safety_verdict(
        matched_allergens=[],
        detected_additives=[],
        profile_allergens=[],
        profile_name="Standard",
    )

    assert verdict == "SAFE"
    assert color == "green"
    assert "SAFE" in summary
    assert len(evaluated) == 0

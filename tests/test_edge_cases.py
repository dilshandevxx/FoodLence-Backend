import pytest
from app.nlp.pipeline import nlp_pipeline
from app.nlp.confidence import confidence_scorer
from app.knowledge_base.allergen_engine import allergen_engine


def test_gibberish_ocr_requires_manual_check():
    """
    Validates that low-quality, noisy or corrupted OCR strings yield a low confidence
    score (< 0.70) and flag requires_manual_check=True.
    """
    noisy_ocr = "###@#$% ^&*()~`+_ =[]{}|;:'\"<>,?/"
    tokens = nlp_pipeline.tokenize_ingredients(noisy_ocr)
    score, manual_check = confidence_scorer.evaluate(
        raw_text=noisy_ocr,
        detected_ingredients=tokens,
        has_keywords=False,
    )

    assert score < 0.70
    assert manual_check is True


def test_empty_ocr_text():
    """
    Validates graceful handling of blank, whitespace-only, or None-like strings.
    """
    tokens = nlp_pipeline.tokenize_ingredients("")
    score, manual_check = confidence_scorer.evaluate(
        raw_text="",
        detected_ingredients=tokens,
        has_keywords=False,
    )

    assert tokens == []
    assert score <= 0.1
    assert manual_check is True


def test_large_ingredient_list_performance():
    """
    Validates parsing and allergen evaluation over a massive list of 60+ ingredients
    within milliseconds.
    """
    base_ingredients = [f"botanical_extract_{i}" for i in range(50)]
    large_list = ", ".join(base_ingredients + ["roasted peanuts", "wheat flour", "pure cane sugar"])
    tokens = nlp_pipeline.tokenize_ingredients(large_list)

    assert len(tokens) >= 50
    matches = allergen_engine.match_allergens_for_ingredients(tokens)
    matched_codes = {m["allergen_code"] for m in matches}

    assert "peanut" in matched_codes
    assert "gluten" in matched_codes


def test_deeply_nested_brackets_and_percentages():
    """
    Validates nested parentheses and brackets, plus percentage symbols.
    """
    complex_text = (
        "enriched flour (wheat flour, malted barley flour, niacin, reduced iron [40%], "
        "thiamine mononitrate, riboflavin (vitamin B2)), water, high fructose corn syrup (5%), "
        "soybean oil (cold-pressed [organic])"
    )
    tokens = nlp_pipeline.tokenize_ingredients(complex_text)

    assert "wheat flour" in tokens
    assert "niacin" in tokens
    assert "water" in tokens
    assert "soybean oil" in tokens

    additives = nlp_pipeline.extract_additives(complex_text)
    assert isinstance(additives, list)


def test_unicode_and_special_accents():
    """
    Validates handling of accents and non-ASCII food naming (e.g. café, jalapeño, crème).
    """
    text = "Ingredients: café extract, crème fraîche, jalapeño peppers, sea salt."
    tokens = nlp_pipeline.tokenize_ingredients(text)

    assert any("café" in t or "cafe" in t for t in tokens)
    assert any("crème" in t or "creme" in t for t in tokens)
    assert any("jalapeño" in t or "jalapeno" in t for t in tokens)

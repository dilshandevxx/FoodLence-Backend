from app.nlp.pipeline import nlp_pipeline


def test_clean_text_noise_prefixes():
    assert nlp_pipeline.clean_text("Ingredients: wheat, sugar, salt") == "wheat, sugar, salt"
    assert nlp_pipeline.clean_text("INGREDIENTS - milk, egg") == "milk, egg"
    assert nlp_pipeline.clean_text("Contains: peanuts, soy") == "peanuts, soy"
    assert nlp_pipeline.clean_text("May contain: tree nuts") == "tree nuts"


def test_nested_sub_ingredients_tokenization():
    text = "enriched wheat flour (flour, niacin, reduced iron, thiamine mononitrate), cane sugar, palm oil"
    tokens = nlp_pipeline.tokenize_ingredients(text)

    assert "enriched wheat flour" in tokens
    assert "flour" in tokens
    assert "niacin" in tokens
    assert "reduced iron" in tokens
    assert "cane sugar" in tokens
    assert "palm oil" in tokens


def test_percentage_stripping():
    text = "whole milk (3.5%), sea salt (0.8%), black pepper (0.1%)"
    tokens = nlp_pipeline.tokenize_ingredients(text)

    assert "whole milk" in tokens
    assert "sea salt" in tokens
    assert "black pepper" in tokens


def test_e_number_and_ins_extraction():
    text = "carbonated water, acidity regulator (E330, INS 331), color (E 102), preservative (INS-211), flavor (E621)"
    additives = nlp_pipeline.extract_additives(text)

    assert "E330" in additives
    assert "E331" in additives
    assert "E102" in additives
    assert "E211" in additives
    assert "E621" in additives


def test_empty_and_whitespace_input():
    assert nlp_pipeline.tokenize_ingredients("") == []
    assert nlp_pipeline.tokenize_ingredients("   \n\t  ") == []
    assert nlp_pipeline.extract_additives("") == []

import re
from typing import List
from app.core.config import settings


class ConfidenceScorer:
    """
    Computes holistic confidence scores based on OCR visual density,
    lexical validity of ingredient strings, and allergen matching proximity.
    """

    @staticmethod
    def calculate_text_quality(raw_text: str) -> float:
        """
        Scores raw OCR text based on alphanumeric density and absence of optical gibberish.
        """
        if not raw_text or len(raw_text.strip()) == 0:
            return 0.0

        clean = raw_text.strip()
        total_chars = len(clean)
        if total_chars < 5:
            return 0.2

        alphanumeric_count = sum(1 for c in clean if c.isalnum() or c.isspace() or c in ",.-();:%")
        density = alphanumeric_count / total_chars

        # Bonus if recognized allergen or ingredient keywords exist
        keyword_bonus = 0.0
        if re.search(r"\b(ingredients?|contains?|may contain|wheat|milk|soya?|peanut|sugar|water|salt|flour)\b", clean, re.IGNORECASE):
            keyword_bonus = 0.15

        base_score = min(1.0, (density * 0.85) + keyword_bonus)
        return round(base_score, 3)

    @classmethod
    def evaluate(
        cls,
        raw_text: str,
        detected_ingredients: List[str],
        has_keywords: bool = False,
    ) -> tuple[float, bool]:
        """
        Computes overall confidence score and determines if manual verification is necessary.
        """
        quality = cls.calculate_text_quality(raw_text)

        # Token count weight: empty or 1-2 chars is low confidence
        if len(detected_ingredients) == 0:
            overall = max(0.1, quality * 0.4)
        else:
            token_factor = min(1.0, len(detected_ingredients) / 5.0)
            keyword_weight = 0.1 if has_keywords else 0.0
            overall = min(1.0, (quality * 0.6) + (token_factor * 0.3) + keyword_weight)

        overall = round(overall, 3)
        requires_manual_check = overall < settings.CONFIDENCE_THRESHOLD

        return overall, requires_manual_check


confidence_scorer = ConfidenceScorer()

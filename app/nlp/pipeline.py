import re
from typing import List, Tuple
from app.nlp.model_loader import model_loader

# Regex to capture E-numbers and INS numbers (e.g. E102, E 621, INS 330, E-211)
E_NUMBER_REGEX = re.compile(r"\b(?:E|INS)\s*[-]?\s*(\d{3,4}[a-zA-Z]?)\b", re.IGNORECASE)

# Common food ingredient noise words & packaging disclaimers
NOISE_PREFIXES = [
    re.compile(r"^ingredients?\s*[:\-]?\s*", re.IGNORECASE),
    re.compile(r"^contains\s*[:\-]?\s*", re.IGNORECASE),
    re.compile(r"^may\s+contain\s*[:\-]?\s*", re.IGNORECASE),
]


class NLPPipeline:
    """
    Ingestion & Tokenization Pipeline for food ingredient text.
    Extracts isolated ingredient entities and detects chemical additive codes.
    """

    def __init__(self) -> None:
        self.loader = model_loader

    def extract_additives(self, text: str) -> List[str]:
        """
        Extracts standardized E-number codes from text (e.g. ['E102', 'E621']).
        """
        matches = E_NUMBER_REGEX.findall(text)
        standardized = []
        for m in matches:
            code = f"E{m.upper().strip()}"
            if code not in standardized:
                standardized.append(code)
        return standardized

    def clean_text(self, text: str) -> str:
        """
        Strips header prefixes, normalized whitespace, and removes surrounding brackets.
        """
        cleaned = text.strip()
        for pattern in NOISE_PREFIXES:
            cleaned = pattern.sub("", cleaned)
        return cleaned.strip()

    def tokenize_ingredients(self, text: str) -> List[str]:
        """
        Splits ingredient text into distinct entity tokens while handling nested parentheses.
        Example: "Wheat flour (flour, iron), sugar, palm oil, salt (0.5%)"
        -> ["Wheat flour", "flour", "iron", "sugar", "palm oil", "salt"]
        """
        cleaned = self.clean_text(text)
        if not cleaned:
            return []

        # Split top-level by comma, semicolon, bullet, newline NOT inside brackets/parentheses
        raw_chunks = []
        current: List[str] = []
        depth = 0
        for char in cleaned:
            if char in "([":
                depth += 1
                current.append(char)
            elif char in ")]":
                if depth > 0:
                    depth -= 1
                current.append(char)
            elif char in ",;•\n" and depth == 0:
                c = "".join(current).strip()
                if c:
                    raw_chunks.append(c)
                current = []
            else:
                current.append(char)
        last_c = "".join(current).strip()
        if last_c:
            raw_chunks.append(last_c)

        ingredients: List[str] = []

        for chunk in raw_chunks:
            chunk = chunk.strip()
            if not chunk or len(chunk) < 2:
                continue

            # Strip percentage annotations: e.g. "salt (0.5%)" or "[40%]"
            chunk = re.sub(r"[\(\[]\s*\d+(?:\.\d+)?\s*%\s*[\)\]]", "", chunk).strip()

            # Extract contents inside inner brackets/parentheses (up to 3 levels deep)
            temp_chunk = chunk
            for _ in range(3):
                sub_matches = re.findall(r"[\(\[]([^\(\)\[\]]+)[\)\]]", temp_chunk)
                if not sub_matches:
                    break
                for sub in sub_matches:
                    for sub_item in re.split(r"[,;]+", sub):
                        cleaned_sub = sub_item.strip()
                        if cleaned_sub and len(cleaned_sub) > 1:
                            ingredients.append(cleaned_sub)
                new_temp = re.sub(r"[\(\[][^\(\)\[\]]*[\)\]]", "", temp_chunk)
                if new_temp == temp_chunk:
                    break
                temp_chunk = new_temp

            # Add main parent ingredient
            clean_parent = re.sub(r"[\(\)\[\]\{\}]", "", temp_chunk).strip()
            if clean_parent and len(clean_parent) > 1:
                ingredients.append(clean_parent)

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for item in ingredients:
            norm = item.lower()
            if norm not in seen:
                seen.add(norm)
                deduped.append(item)

        return deduped

        return deduped

    def process(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Processes text and returns a tuple of (ingredient_entities, additive_e_numbers).
        """
        additives = self.extract_additives(text)
        entities = self.tokenize_ingredients(text)

        # Use spaCy if loaded for enhanced entity enrichment
        nlp = self.loader.nlp
        if nlp is not None and text:
            try:
                doc = nlp(text)
                # Enhance with noun chunks if any were missed
                for chunk in doc.noun_chunks:
                    clean_chunk = self.clean_text(chunk.text)
                    if clean_chunk and len(clean_chunk) > 2 and clean_chunk.lower() not in [e.lower() for e in entities]:
                        entities.append(clean_chunk)
            except Exception:
                pass

        return entities, additives


nlp_pipeline = NLPPipeline()

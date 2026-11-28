"""Controlled, transparent synthetic forms from the bundled taxonomy."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict
from typing import Iterable

from .taxonomy import TAXONOMY, TaxonomyClass

METHODS = {"canonical_exact", "alias_exact", "case_format", "spacing_format", "punctuation_format", "ocr_confusable"}
PROVENANCE_FIELDS = ("candidate_id", "ingredient_text", "normalized_text", "canonical_class_id", "canonical_name", "source_type", "source_dataset", "source_reference", "parent_example_id", "generation_method", "is_synthetic", "label_method", "validation_method", "validation_status", "validation_reason", "review_status", "dataset_version")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).strip().casefold())


def _id(parent: str, text: str, method: str) -> str:
    return hashlib.sha256(f"{parent}|{method}|{text}".encode()).hexdigest()[:24]


def generate_candidates(classes: Iterable[TaxonomyClass] = TAXONOMY, seed: int = 5104) -> list[dict]:
    """Generate a small deterministic pool; OCR variants require explicit alias evidence.

    Canonical labels and aliases are semantic forms. Case, whitespace, punctuation,
    and OCR edits are surface variants and are counted separately by normalized text.
    No E-number output is generated unless present on a verified taxonomy class.
    """
    del seed  # Generation intentionally uses no randomness.
    rows = []
    for item in classes:
        parent = f"taxonomy:{item.class_id}"
        baseforms = [(item.canonical_name, "canonical_exact")]
        baseforms.extend((alias, "alias_exact") for alias in item.aliases)
        for form, method in baseforms:
            rows.append(_row(item, form, parent, method, form))
            # Explicitly surface-only forms; normalization merges case/spacing.
            rows.append(_row(item, form.upper(), parent, "case_format", form))
            if " " in form:
                rows.append(_row(item, form.replace(" ", "  "), parent, "spacing_format", form))
            if " " in form:
                rows.append(_row(item, form.replace(" ", "-"), parent, "punctuation_format", form))
            # OCR noise is restricted to aliases verified by taxonomy evidence.
            if method == "alias_exact" and item.verification_status == "verified":
                noisy = form.replace("e", "3", 1) if "e" in form else ""
                if noisy and noisy != form:
                    rows.append(_row(item, noisy, parent, "ocr_confusable", form))
    return rows


def _row(item: TaxonomyClass, text: str, parent: str, method: str, semantic_form: str) -> dict:
    return {"candidate_id": _id(parent, text, method), "ingredient_text": text,
        "normalized_text": normalize(text), "canonical_class_id": item.class_id,
        "canonical_name": item.canonical_name, "source_type": "synthetic_taxonomy",
        "source_dataset": "FoodLence V4 taxonomy", "source_reference": item.taxonomy_source,
        "parent_example_id": parent, "generation_method": method, "is_synthetic": True,
        "label_method": "synthetic_parent_mapping", "validation_method": "structural_taxonomy_rule",
        "validation_status": "accepted", "validation_reason": f"surface form of {semantic_form}; class remains {item.verification_status}",
        "review_status": "not_human_reviewed", "dataset_version": "4.0.0",
        "semantic_form": normalize(semantic_form)}

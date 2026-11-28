"""Deterministic exact-match recognizer for the experimental FoodLence V4 vocabulary."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

STATUSES = {"canonical_exact", "evidence_supported_exact", "provisional_exact", "synthetic_exact", "ambiguous", "unresolved"}


def normalize_lookup(value: object) -> str:
    """Normalize Unicode, case, whitespace, and punctuation conservatively."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = text.replace(chr(0x2019), chr(39)).replace(chr(0x2018), chr(39)).replace(chr(0x2013), chr(45)).replace(chr(0x2014), chr(45))
    text = re.sub(r"\s+", " ", text)
    # Normalize surrounding punctuation only. Internal punctuation is retained.
    return re.sub(r"^[\s,.;:!?]+|[\s,.;:!?]+$", "", text)


class IngredientRecognizer:
    def __init__(self, vocabulary_path: Path, examples_path: Path | None = None):
        self.vocabulary_path = Path(vocabulary_path)
        self.examples_path = Path(examples_path) if examples_path else None
        self.index: dict[str, list[dict[str, str]]] = defaultdict(list)
        with self.vocabulary_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                key = normalize_lookup(row.get("normalized_term") or row.get("term"))
                if key:
                    self.index[key].append(row)
        self.provenance: dict[str, list[dict[str, str]]] = defaultdict(list)
        if self.examples_path and self.examples_path.exists():
            with self.examples_path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    key = normalize_lookup(row.get("normalized_text"))
                    original_key = normalize_lookup(row.get("original_text"))
                    if key:
                        self.provenance[key].append({k: row.get(k, "") for k in ("example_id", "source_dataset", "source_row_id", "source_reference", "source_type", "evidence_tier", "review_status")})
                        if str(row.get("is_synthetic", "")).casefold() == "true":
                            synthetic = {"term": row.get("original_text", ""), "normalized_term": key,
                                "entry_kind": "synthetic_surface_form", "class_id": row.get("proposed_class_id", ""),
                                "canonical_name": row.get("proposed_class_name", ""), "evidence_tier": "C",
                                "review_status": row.get("review_status", "not_human_reviewed")}
                            self.index[key].append(synthetic)
                            # Preserve the exact generated surface too; normalization may differ
                            # from the parent phrase (for example, hyphen versus space).
                            if original_key and original_key != key:
                                self.index[original_key].append(synthetic)
                                self.provenance[original_key].append(self.provenance[key][-1])

    def recognize(self, phrase: object, include_provenance: bool = True) -> dict:
        original = "" if phrase is None else str(phrase)
        normalized = normalize_lookup(original)
        matches = self.index.get(normalized, [])
        common = {"original_input_text": original, "normalized_input_text": normalized, "matched_vocabulary_term": "", "concept_id": "", "concept_name": "", "evidence_tier": "", "source_provenance": [], "review_status": "not_human_reviewed", "ambiguity_details": [], "verification_limitation": "Exact vocabulary lookup only; no scientific identity or safety conclusion is implied."}
        if len(matches) > 1:
            identities = {(r.get("class_id", ""), r.get("canonical_name", "")) for r in matches}
            if len(identities) > 1:
                common.update(match_status="ambiguous", ambiguity_details=[{"concept_id": r.get("class_id", ""), "concept_name": r.get("canonical_name", ""), "evidence_tier": r.get("evidence_tier", ""), "term": r.get("term", "")} for r in sorted(matches, key=lambda item: (item.get("class_id", ""), item.get("term", "")))])
                return common
        if not normalized or not matches:
            common["match_status"] = "unresolved"
            common["verification_limitation"] = "No exact vocabulary match; identity remains unresolved."
            return common
        row = sorted(matches, key=lambda r: (r.get("entry_kind") != "canonical_class", r.get("class_id", ""), r.get("term", "")))[0]
        cid = row.get("class_id", "")
        tier = row.get("evidence_tier", "")
        if tier == "C":
            status = "synthetic_exact"
        elif cid.startswith("FL-"):
            status = "canonical_exact"
        elif tier == "A":
            status = "evidence_supported_exact"
        else:
            status = "provisional_exact"
        common.update(match_status=status, matched_vocabulary_term=row.get("term", ""), concept_id=cid,
                      concept_name=row.get("canonical_name", ""), evidence_tier=tier,
                      review_status=row.get("review_status") or "not_human_reviewed")
        if include_provenance:
            common["source_provenance"] = self.provenance.get(normalized, [])
        if tier == "C":
            common["verification_limitation"] = "Exact synthetic surface-form match only; the parent taxonomy class remains scientifically unverified."
        elif cid.startswith("FL-"):
            common["verification_limitation"] = "Canonical taxonomy entry is structurally present but scientifically unverified."
        else:
            common["verification_limitation"] = "Exact match to an evidence or provisional vocabulary term is not independent scientific or human verification."
        return common


def read_phrases_csv(path: Path, column: str | None = None) -> list[str]:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        selected = column or next((name for name in ("ingredient", "phrase", "text", "ingredient_text", "candidate_phrase") if name in fields), None)
        if selected not in fields:
            raise ValueError(f"input CSV requires a phrase column; available columns: {fields}")
        return [row.get(selected, "") or "" for row in reader]


def write_results(path: Path, rows: list[dict]) -> None:
    fields = ["original_input_text", "normalized_input_text", "match_status", "matched_vocabulary_term", "concept_id", "concept_name", "evidence_tier", "source_provenance", "review_status", "ambiguity_details", "verification_limitation"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "source_provenance": json.dumps(row["source_provenance"], ensure_ascii=False), "ambiguity_details": json.dumps(row["ambiguity_details"], ensure_ascii=False)})


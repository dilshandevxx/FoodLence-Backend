"""Deterministic structural validation for FoodLence canonical classes."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict

from .taxonomy import TaxonomyClass, TAXONOMY

E_NUMBER_PATTERN = re.compile(r"^E\d{3,4}[A-Z]?$", re.IGNORECASE)
ALLOWED_TYPES = {"ingredient", "additive"}
REQUIRED = ("class_id", "canonical_name", "type", "category", "taxonomy_source", "verification_status")


def validate_taxonomy(classes: tuple[TaxonomyClass, ...] | list[TaxonomyClass] | None = None) -> dict:
    classes = tuple(TAXONOMY if classes is None else classes)
    issues: list[dict[str, str]] = []
    ids: dict[str, int] = defaultdict(int)
    names: dict[str, int] = defaultdict(int)
    aliases: dict[str, set[str]] = defaultdict(set)
    e_numbers: dict[str, set[str]] = defaultdict(set)
    for item in classes:
        data = asdict(item)
        for field in REQUIRED:
            if not str(data.get(field, "")).strip():
                issues.append({"code": "missing_required_field", "class_id": item.class_id, "field": field})
        ids[item.class_id] += 1
        names[item.canonical_name.strip().casefold()] += 1
        if item.type not in ALLOWED_TYPES:
            issues.append({"code": "invalid_type", "class_id": item.class_id, "value": item.type})
        if item.e_number:
            if not E_NUMBER_PATTERN.fullmatch(item.e_number):
                issues.append({"code": "invalid_e_number_format", "class_id": item.class_id, "value": item.e_number})
            e_numbers[item.e_number.upper()].add(item.class_id)
        for alias in item.aliases:
            if alias.strip():
                aliases[alias.strip().casefold()].add(item.class_id)
        if not item.taxonomy_source.strip():
            issues.append({"code": "missing_taxonomy_provenance", "class_id": item.class_id})
    for class_id, count in ids.items():
        if count > 1:
            issues.append({"code": "duplicate_class_id", "class_id": class_id})
    for name, count in names.items():
        if count > 1:
            issues.append({"code": "duplicate_canonical_name", "name": name})
    canonical_owners = {item.canonical_name.strip().casefold(): item.class_id for item in classes}
    for alias, owners in aliases.items():
        owners |= ({canonical_owners[alias]} if alias in canonical_owners else set())
        if len(owners) > 1:
            issues.append({"code": "conflicting_alias", "alias": alias, "class_ids": ",".join(sorted(owners))})
    for code, owners in e_numbers.items():
        if len(owners) > 1:
            issues.append({"code": "contradictory_e_number_mapping", "e_number": code, "class_ids": ",".join(sorted(owners))})
    structurally_valid = not issues
    return {
        "class_count": len(classes),
        "target_class_count_met": 180 <= len(classes) <= 200,
        "structurally_valid": structurally_valid,
        "scientifically_verified": all(item.verification_status == "verified" for item in classes),
        "verification_status_counts": {status: sum(x.verification_status == status for x in classes) for status in sorted({x.verification_status for x in classes})},
        "issues": issues,
    }


def validate_generated(candidates: list[dict], classes: tuple[TaxonomyClass, ...] | list[TaxonomyClass] | None = None) -> dict:
    """Check generated candidate structure and contradictory normalized labels."""
    classes = tuple(TAXONOMY if classes is None else classes)
    known = {item.class_id: item for item in classes}
    issues = []
    owners = defaultdict(set)
    for row in candidates:
        cid = row.get("canonical_class_id", "")
        method = row.get("generation_method", "")
        missing = [field for field in ("candidate_id", "ingredient_text", "normalized_text", "source_reference", "parent_example_id", "review_status") if not str(row.get(field, "")).strip()]
        if missing: issues.append({"code":"missing_provenance","candidate_id":row.get("candidate_id",""),"fields":",".join(missing)})
        if cid not in known: issues.append({"code":"invalid_class_reference","candidate_id":row.get("candidate_id",""),"class_id":cid})
        if not row.get("ingredient_text", "").strip(): issues.append({"code":"empty_phrase","candidate_id":row.get("candidate_id","")})
        if row.get("is_synthetic") is not True: issues.append({"code":"invalid_synthetic_flag","candidate_id":row.get("candidate_id","")})
        if method not in {"canonical_exact","alias_exact","case_format","spacing_format","punctuation_format","ocr_confusable"}: issues.append({"code":"invalid_generation_method","candidate_id":row.get("candidate_id","")})
        if row.get("review_status") != "not_human_reviewed": issues.append({"code":"unsupported_review_claim","candidate_id":row.get("candidate_id","")})
        owners[row.get("normalized_text", "")].add(cid)
    conflicts = [phrase for phrase, ids in owners.items() if len(ids) > 1]
    return {"candidate_count":len(candidates),"structurally_valid":not issues and not conflicts,"issues":issues,"conflicting_normalized_phrases":conflicts,"semantic_verification":"not established by structural validation"}

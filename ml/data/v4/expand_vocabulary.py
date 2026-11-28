"""Conservative, non-human-reviewed vocabulary expansion for FoodLence V4."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .discover_vocabulary import normalize_candidate
from .prioritize_vocabulary import candidate_id as vocabulary_candidate_id
from .review_vocabulary import read_csv, sha256_file, write_csv
from .taxonomy import TAXONOMY
from .validate import validate_taxonomy

VERSION = "FoodLence V4 Phase 7A"
ALLOWED_SOURCE_CATEGORIES = {"possible_new_ingredient", "possible_additive"}
E_NUMBER_RE = re.compile(r"(?<![a-z0-9])e\s*[- ]?\s*\d{3,4}[a-z]?(?![a-z0-9])", re.I)
WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")
FORBIDDEN_QUALIFIERS = {
    "organic", "natural", "artificial", "gluten free", "non gmo", "non-gmo", "reduced",
    "low fat", "fat free", "pasteurized", "pasteurised", "part skim", "farm raised",
    "expeller pressed", "extra virgin", "non hydrogenated", "hydrogenated", "free from",
}
FORBIDDEN_FUNCTION_CONTEXT = {
    "emulsifier", "acidity regulator", "anti caking", "anticaking", "enriching substance",
    "stabilizer", "stabiliser", "preservative", "flavoring agent", "flavouring agent",
    "coloring agent", "colouring agent", "anti oxidant",
}

# These explicit identity/alias relationships were already recorded in the
# project evidence registries. Tier A does not imply human review or approval.
TIER_A_RULES = {
    "baking soda": {
        "class_id": "FL-160", "canonical_name": "sodium bicarbonate", "entry_kind": "authority_supported_alias",
        "relation": "synonym", "source_id": "FDA-FS-SODIUMBICARBONATE",
        "url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=SODIUMBICARBONATE&set=FoodSubstances",
        "summary": "FDA lists baking soda as another name for sodium bicarbonate.",
        "limitations": "Source occurrences may refer to a mixture/product; the mapping is not human reviewed.",
    },
    "food starch modified": {
        "class_id": "", "canonical_name": "starch, food, modified", "entry_kind": "authority_supported_provisional_concept",
        "relation": "listed_other_name", "source_id": "FDA-FS-STARCHFOODMODIFIED",
        "url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=STARCHFOODMODIFIED&set=FoodSubstances",
        "summary": "FDA identifies STARCH, FOOD, MODIFIED and lists FOOD STARCH, MODIFIED as another name.",
        "limitations": "Does not identify a source-specific modified starch such as modified corn starch.",
    },
    "agar agar": {
        "class_id": "", "canonical_name": "agar", "entry_kind": "authority_supported_provisional_concept",
        "relation": "listed_other_name", "source_id": "FDA-FS-AGAR",
        "url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=AGAR&set=FoodSubstances",
        "summary": "FDA lists AGAR-AGAR as another name for AGAR (GELIDIUM SPP.).",
        "limitations": "The source occurrence does not establish the species/source identity.",
    },
    "mono and diglycerides": {
        "class_id": "", "canonical_name": "mono- and diglycerides", "entry_kind": "authority_supported_provisional_concept",
        "relation": "formatting_normalized_official_term", "source_id": "FDA-FS-MONOANDDIGLYCERIDES",
        "url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=MONOANDDIGLYCERIDES&set=FoodSubstances",
        "summary": "FDA's substance entry is MONO- AND DIGLYCERIDES and includes related mixed mono- and diglyceride names.",
        "limitations": "Refers to a grouped glyceride mixture; do not split or merge with chemically distinct glycerides.",
    },
    "sodium alginate": {
        "class_id": "", "canonical_name": "alginate, sodium", "entry_kind": "authority_supported_provisional_concept",
        "relation": "listed_other_name", "source_id": "FDA-FS-ALGINATESODIUM",
        "url": "https://hfpappexternal.fda.gov/scripts/Fdcc/index.cfm?id=ALGINATESODIUM&set=FoodSubstances",
        "summary": "FDA entry ALGINATE, SODIUM lists SODIUM ALGINATE as another name.",
        "limitations": "No equivalent canonical class exists in the current taxonomy.",
    },
}
UNSUPPORTED_NEAR_MATCHES = {
    "mono diglycerides": "FDA records MONO- AND DIGLYCERIDES; omission of 'and' is not accepted as an alias.",
    "mono diglyceride": "No authoritative evidence supports this singular form as equivalent to mono- and diglycerides.",
}

EXAMPLE_FIELDS = [
    "example_id", "original_text", "normalized_text", "proposed_class_id", "proposed_class_name",
    "concept_namespace", "source_type", "source_dataset", "source_file_hash", "source_row_id", "source_text",
    "source_reference", "generation_method", "is_synthetic", "label_method", "evidence_tier",
    "evidence_source_id", "evidence_url", "evidence_summary", "validation_status", "validation_reason",
    "review_status", "semantic_form", "source_candidate_id", "discovery_category",
    "source_provenance", "provenance_records",
]
VOCAB_FIELDS = [
    "vocabulary_id", "term", "normalized_term", "entry_kind", "class_id", "canonical_name",
    "taxonomy_type", "discovery_category", "evidence_tier", "relationship", "evidence_source_id",
    "evidence_url", "evidence_summary", "evidence_limitations", "taxonomy_verification_status",
    "review_status", "integration_status", "source_candidate_ids", "source_occurrence_count",
]
UNRESOLVED_FIELDS = [
    "candidate_id", "candidate_phrase", "normalized_phrase", "occurrence_count", "discovery_category",
    "priority_score", "evidence_status", "evidence_source_id", "evidence_url", "evidence_tier",
    "unresolved_reason", "source_references", "review_status",
]
QUARANTINE_FIELDS = EXAMPLE_FIELDS + ["quarantine_reason"]


def stable_id(namespace: str, normalized_phrase: str) -> str:
    if namespace not in {"PVA", "PVB"}:
        raise ValueError("provisional namespace must be PVA or PVB")
    digest = hashlib.sha256(("foodlence-v4-phase7a\0" + normalize_candidate(normalized_phrase)).encode("utf-8")).hexdigest()[:20].upper()
    return f"{namespace}-{digest}"


def build_taxonomy_index(classes=TAXONOMY) -> tuple[dict[str, set[str]], dict[str, object]]:
    owners: dict[str, set[str]] = defaultdict(set)
    by_id = {item.class_id: item for item in classes}
    for item in classes:
        owners[normalize_candidate(item.canonical_name)].add(item.class_id)
        for alias in item.aliases:
            owners[normalize_candidate(alias)].add(item.class_id)
    return owners, by_id


def _source_structure_issue(phrase: str) -> str:
    if len(phrase) < 3 or len(phrase) > 80:
        return "phrase length outside conservative 3-80 character range"
    if not re.fullmatch(r"[a-z][a-z' -]*[a-z]", phrase):
        return "contains unsupported punctuation, digits, non-Latin characters, or malformed token boundaries"
    if re.search(r"\s{2,}|-{2,}|\s-|- ", phrase):
        return "contains irregular whitespace or dash formatting"
    words = WORD_RE.findall(phrase)
    if not 1 <= len(words) <= 5 or " ".join(words) != phrase.replace("-", " "):
        return "does not form a simple one-to-five-word ingredient term"
    if re.search(r"\b(?:and|or)\b", phrase):
        return "contains a conjunction; possible compound or list phrase"
    if any(term in phrase for term in FORBIDDEN_QUALIFIERS):
        return "contains a source, processing, dietary, or product qualifier requiring contextual review"
    if any(term in phrase for term in FORBIDDEN_FUNCTION_CONTEXT):
        return "contains a function or context descriptor mixed with a possible ingredient name"
    if re.search(r"\b(?:contains|may contain|product|preparation|made with|with added|ingredients?)\b", phrase):
        return "contains product or ingredient-list description wording"
    return ""


def inspect_source_term(row: dict, taxonomy_owners: dict[str, set[str]], authoritative_e_map: dict[str, str] | None = None) -> dict:
    """Assign a conservative candidate tier and proposed class ID."""
    phrase = str(row.get("normalized_phrase") or row.get("candidate_phrase") or "")
    normalized = normalize_candidate(phrase)
    category = row.get("discovery_category", "")
    if not normalized:
        return {"tier": "D", "class_id": "", "canonical_name": "", "reason": "empty normalized phrase"}
    codes = [match.group(0).upper().replace(" ", "").replace("-", "") for match in E_NUMBER_RE.finditer(normalized)]
    authoritative_e_map = authoritative_e_map or {}
    if codes:
        if len(codes) == 1 and normalized.upper() == codes[0] and codes[0] in authoritative_e_map:
            cid = authoritative_e_map[codes[0]]
            return {"tier": "A", "class_id": cid, "canonical_name": "", "reason": "exact E-number mapping from a verified taxonomy entry",
                    "rule": {"source_id": "verified_taxonomy_e_number", "url": "", "entry_kind": "verified_taxonomy_e_number", "summary": "Exact E-number mapping from a verified taxonomy entry.", "limitations": "Not human reviewed."}}
        return {"tier": "D", "class_id": "", "canonical_name": "", "reason": "E-number-like phrase lacks an authoritative exact mapping"}
    owners = taxonomy_owners.get(normalized, set())
    if len(owners) > 1:
        return {"tier": "D", "class_id": "", "canonical_name": "", "reason": "normalized term conflicts across canonical classes or aliases"}
    if len(owners) == 1:
        cid = next(iter(owners))
        return {"tier": "B", "class_id": cid, "canonical_name": "", "reason": "exact normalized taxonomy term; taxonomy verification status remains unchanged"}
    rule = TIER_A_RULES.get(normalized)
    if rule:
        cid = rule["class_id"] or stable_id("PVA", normalized)
        return {"tier": "A", "class_id": cid, "canonical_name": rule["canonical_name"], "reason": rule["summary"], "rule": rule}
    if normalized in UNSUPPORTED_NEAR_MATCHES:
        return {"tier": "D", "class_id": "", "canonical_name": "", "reason": UNSUPPORTED_NEAR_MATCHES[normalized]}
    if category not in ALLOWED_SOURCE_CATEGORIES:
        return {"tier": "D", "class_id": "", "canonical_name": "", "reason": f"discovery category '{category}' is not eligible for standalone provisional mapping"}
    issue = _source_structure_issue(normalized)
    if issue:
        return {"tier": "D", "class_id": "", "canonical_name": "", "reason": issue}
    return {"tier": "B", "class_id": stable_id("PVB", normalized), "canonical_name": phrase,
            "reason": "source-observed phrase passed conservative structure checks; identity and category remain unverified"}


def validate_mapping(row: dict, canonical_ids: set[str]) -> str:
    cid = str(row.get("proposed_class_id", ""))
    tier = row.get("evidence_tier", "")
    if not cid:
        return "missing proposed class ID"
    if cid.startswith("FL-") and cid not in canonical_ids:
        return "invalid canonical class reference"
    if cid.startswith(("PVA-", "PVB-")):
        if not re.fullmatch(r"PV[AB]-[0-9A-F]{20}", cid):
            return "invalid provisional class ID format"
        if (tier == "A" and not cid.startswith("PVA-")) or (tier == "B" and not cid.startswith("PVB-")):
            return "provisional namespace does not match evidence tier"
    elif not cid.startswith("FL-"):
        return "unknown class ID namespace"
    return ""


def validate_e_number(phrase: str, authoritative_e_map: dict[str, str]) -> tuple[bool, str]:
    codes = [match.group(0).upper().replace(" ", "").replace("-", "") for match in E_NUMBER_RE.finditer(phrase)]
    if not codes:
        return True, "no E-number token"
    targets = {authoritative_e_map.get(code) for code in codes}
    if None in targets or "" in targets:
        return False, "E-number-like term has no explicitly authoritative mapping"
    if len(targets) != 1:
        return False, "multiple E-number tokens resolve to conflicting classes"
    return True, next(iter(targets))


def reconcile_example_conflicts(rows: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Quarantine every example in a normalized phrase with conflicting class IDs."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = normalize_candidate(row.get("normalized_text", ""))
        if key:
            groups[key].append(row)
    conflicts = {key for key, group in groups.items() if len({r.get("proposed_class_id", "") for r in group if r.get("proposed_class_id")}) > 1}
    accepted, quarantined = [], []
    for row in rows:
        key = normalize_candidate(row.get("normalized_text", ""))
        if key in conflicts:
            quarantined.append({**row, "validation_status": "quarantined_conflicting_label", "quarantine_reason": "same normalized phrase has multiple proposed class IDs"})
        else:
            accepted.append(row)
    return accepted, quarantined, len(conflicts)


def _read(path: Path) -> list[dict[str, str]]:
    return read_csv(path)[0]


def _load_evidence(phase6b2: Path, phase6b4: Path) -> dict[str, dict]:
    evidence = {}
    for path in (phase6b2 / "candidate_evidence_registry.csv", phase6b4 / "pilot_evidence_registry.csv"):
        if not path.exists():
            continue
        for row in _read(path):
            key = normalize_candidate(row.get("normalized_phrase") or row.get("candidate_phrase") or "")
            if key:
                evidence[key] = row
    return evidence


def _validate_rule_provenance(phase6b2: Path, phase6b4: Path) -> dict[str, dict]:
    phase6b2_evidence = {normalize_candidate(r.get("normalized_phrase", "")): r for r in _read(phase6b2 / "candidate_evidence_registry.csv")}
    phase6b4_evidence = {normalize_candidate(r.get("normalized_phrase") or r.get("candidate_phrase", "")): r for r in _read(phase6b4 / "pilot_evidence_registry.csv")}
    for phrase, rule in TIER_A_RULES.items():
        row = phase6b4_evidence.get(phrase) or phase6b2_evidence.get(phrase)
        if row is None or row.get("evidence_status") != "evidence_found":
            raise ValueError(f"Tier A evidence missing from Phase 6B sources: {phrase}")
        url = row.get("source_url") or row.get("evidence_url") or row.get("evidence_url", "")
        if url != rule["url"]:
            raise ValueError(f"Tier A evidence URL differs from recorded source for {phrase}")
    return _load_evidence(phase6b2, phase6b4)


def _baseline_example(row: dict) -> dict:
    synthetic = str(row.get("is_synthetic", "")).casefold() == "true"
    return {
        "example_id": row.get("candidate_id", ""), "original_text": row.get("ingredient_text", ""),
        "normalized_text": normalize_candidate(row.get("normalized_text", "")),
        "proposed_class_id": row.get("canonical_class_id", ""), "proposed_class_name": row.get("canonical_name", ""),
        "concept_namespace": "canonical", "source_type": "synthetic" if synthetic else "source_derived",
            "source_dataset": row.get("source_dataset", ""),
            "source_file_hash": row.get("source_reference", "").removeprefix("sha256:") if row.get("source_reference", "").startswith("sha256:") else "",
        "source_row_id": row.get("source_row_id", ""), "source_text": row.get("source_text", ""),
        "source_reference": row.get("source_reference", ""),
        "generation_method": row.get("generation_method", "source_observed" if not synthetic else "controlled_existing_variant"),
        "is_synthetic": str(synthetic), "label_method": row.get("label_method", ""),
        "evidence_tier": "C" if synthetic else "B", "evidence_source_id": "", "evidence_url": "",
        "evidence_summary": "Existing Phase 4B baseline; source label remains provisional and taxonomy unverified." if not synthetic else "Existing controlled synthetic example derived from unchanged taxonomy.",
        "source_provenance": row.get("contributor_provenance", ""),
        "provenance_records": row.get("provenance_records", ""),
        "validation_status": row.get("validation_status", ""), "validation_reason": row.get("validation_reason", ""),
        "review_status": "not_human_reviewed", "semantic_form": row.get("semantic_form", ""),
        "source_candidate_id": row.get("candidate_id", ""), "discovery_category": "existing_phase4b_baseline",
    }


def _unmatched_example(row: dict, normalized: str, discovery: dict | None, decision: dict) -> dict:
    rule = decision.get("rule", {})
    tier, cid = decision.get("tier", "D"), decision.get("class_id", "")
    class_name = decision.get("canonical_name", "")
    status = "accepted_automatic_provisional" if tier in {"A", "B"} and cid else "unresolved"
    return {
        "example_id": row.get("candidate_id", ""), "original_text": row.get("ingredient_text", ""),
        "normalized_text": normalized, "proposed_class_id": cid, "proposed_class_name": decision.get("canonical_name", ""),
        "concept_namespace": cid.split("-", 1)[0] if cid else "", "source_type": "source_derived",
        "source_dataset": row.get("source_dataset", ""), "source_file_hash": row.get("source_file_hash", ""),
        "source_row_id": row.get("source_row_id", ""), "source_text": row.get("source_text", ""),
        "source_reference": f"{row.get('source_dataset', '')}#{row.get('source_row_id', '')}",
        "generation_method": "source_observed", "is_synthetic": "False",
        "label_method": "authoritative_identity_rule" if tier == "A" else "source_phrase_provisional_id" if tier == "B" else "",
        "evidence_tier": tier, "evidence_source_id": rule.get("source_id", ""), "evidence_url": rule.get("url", ""),
        "evidence_summary": rule.get("summary", ""), "validation_status": status,
        "source_provenance": json.dumps({k: row.get(k, "") for k in ("candidate_id", "source_dataset", "source_file_hash", "source_row_id", "source_text", "ingredient_text")}, ensure_ascii=False, sort_keys=True),
        "provenance_records": "",
        "validation_reason": decision.get("reason", ""), "review_status": "not_human_reviewed",
        "semantic_form": (normalize_candidate(class_name) if cid.startswith("FL-") else cid) if status.startswith("accepted") else "", "source_candidate_id": row.get("candidate_id", ""),
        "discovery_category": (discovery or {}).get("discovery_category", ""),
    }


def _vocab_row(cid: str, term: str, decision: dict, inventory_row: dict, occurrences: int, rule: dict, entry_kind: str) -> dict:
    category = inventory_row.get("discovery_category", "")
    concept_type = "additive_candidate" if category == "possible_additive" else "ingredient_candidate" if category == "possible_new_ingredient" else "unresolved_candidate_type"
    return {
        "vocabulary_id": f"{cid}:{normalize_candidate(term)}", "term": term, "normalized_term": normalize_candidate(term),
        "entry_kind": entry_kind, "class_id": cid, "canonical_name": decision.get("canonical_name", term),
        "taxonomy_type": concept_type if cid.startswith("PV") else "additive", "discovery_category": category,
        "evidence_tier": decision["tier"], "relationship": rule.get("relation", "source_observed_phrase"),
        "evidence_source_id": rule.get("source_id", ""), "evidence_url": rule.get("url", ""),
        "evidence_summary": rule.get("summary", decision.get("reason", "")), "evidence_limitations": rule.get("limitations", ""),
        "taxonomy_verification_status": "not_applicable_provisional" if cid.startswith("PV") else "unverified",
        "review_status": "not_human_reviewed", "integration_status": "phase7a_separate_vocabulary_only",
        "source_candidate_ids": inventory_row.get("candidate_id", ""), "source_occurrence_count": occurrences,
    }


def expand_vocabulary(phase2_dir: Path, phase4b_dir: Path, phase6b1_dir: Path, phase6b2_dir: Path,
                      phase6b4_dir: Path, output_dir: Path, taxonomy=TAXONOMY) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing Phase 7A output: {output_dir}")
    taxonomy_report = validate_taxonomy(taxonomy)
    if not taxonomy_report["structurally_valid"]:
        raise ValueError("existing taxonomy fails structural validation")
    evidence_by_phrase = _validate_rule_provenance(phase6b2_dir, phase6b4_dir)
    inventory = _read(phase6b1_dir / "vocabulary_candidates.csv")
    source_rows = _read(phase2_dir / "unmatched_candidates.csv")
    baseline = _read(phase4b_dir / "ingredients_all.csv")
    shortlist = _read(phase6b2_dir / "priority_shortlist.csv")
    owners, by_id = build_taxonomy_index(taxonomy)
    canonical_ids = set(by_id)
    authoritative_e_map = {}
    for cls in taxonomy:
        if cls.e_number and cls.verification_status == "verified":
            code = cls.e_number.upper().replace(" ", "").replace("-", "")
            if code in authoritative_e_map and authoritative_e_map[code] != cls.class_id:
                raise ValueError(f"conflicting verified E-number mapping: {code}")
            authoritative_e_map[code] = cls.class_id
    inventory_by_phrase = {normalize_candidate(r.get("normalized_phrase", "")): r for r in inventory}
    if len(inventory_by_phrase) != len(inventory):
        raise ValueError("Phase 6B-1 inventory collides after shared deterministic normalization")
    if sum(int(r.get("frequency") or 0) for r in inventory) != len(source_rows):
        raise ValueError("Phase 6B-1 phrase frequencies do not reconcile to Phase 2 unmatched occurrences")
    decisions: dict[str, dict] = {}
    unresolved = []
    shortlist_by_phrase = {normalize_candidate(r.get("normalized_phrase", "")): r for r in shortlist}
    for key, item in inventory_by_phrase.items():
        item["candidate_id"] = shortlist_by_phrase.get(key, {}).get("candidate_id") or vocabulary_candidate_id(key)
    for item in inventory:
        key = normalize_candidate(item.get("normalized_phrase", ""))
        decision = inspect_source_term(item, owners, authoritative_e_map)
        if decision.get("class_id") in by_id and not decision.get("canonical_name"):
            decision["canonical_name"] = by_id[decision["class_id"]].canonical_name
        if decision["tier"] == "A":
            rule = decision["rule"]
            if rule.get("source_id") == "verified_taxonomy_e_number":
                if decision["class_id"] not in by_id or by_id[decision["class_id"]].verification_status != "verified":
                    raise ValueError(f"unverified taxonomy E-number mapping for {key}")
            else:
                ev = evidence_by_phrase.get(key, {})
                ev_url = ev.get("source_url") or ev.get("evidence_url") or ev.get("evidence_urls", "")
                if ev.get("evidence_status") != "evidence_found" or ev_url != rule["url"]:
                    raise ValueError(f"authoritative evidence does not match the Phase 6B record for {key}")
        decisions[key] = decision
        if decision["tier"] == "D":
            short = shortlist_by_phrase.get(key, {})
            unresolved.append({
                "candidate_id": short.get("candidate_id", ""), "candidate_phrase": item.get("candidate_phrase", ""),
                "normalized_phrase": item.get("normalized_phrase", ""), "occurrence_count": item.get("frequency", ""),
                "discovery_category": item.get("discovery_category", ""), "priority_score": short.get("priority_score", ""),
                "evidence_status": short.get("evidence_status", "not_checked"), "evidence_source_id": "",
                "evidence_url": "", "evidence_tier": "D", "unresolved_reason": decision["reason"],
                "source_references": item.get("source_references", "[]"), "review_status": "not_human_reviewed",
            })

    new_examples, quarantine = [], []
    occurrence_tiers = Counter()
    missing_inventory_count = 0
    for row in source_rows:
        key = normalize_candidate(row.get("normalized_text") or row.get("ingredient_text", ""))
        inv = inventory_by_phrase.get(key)
        if inv is None:
            missing_inventory_count += 1
            bad = _unmatched_example(row, key, None, {"tier": "D", "reason": "no matching Phase 6B-1 discovery record"})
            quarantine.append({**bad, "validation_status": "quarantined_missing_discovery", "quarantine_reason": "source occurrence is absent from normalized discovery inventory"})
            continue
        decision = decisions[key]
        occurrence_tiers[decision["tier"]] += 1
        output_row = _unmatched_example(row, key, inv, decision)
        if decision["tier"] in {"A", "B"}:
            issue = validate_mapping(output_row, canonical_ids)
            if issue:
                quarantine.append({**output_row, "validation_status": "quarantined_invalid_mapping", "quarantine_reason": issue})
            else:
                new_examples.append(output_row)
        else:
            new_examples.append(output_row)

    baseline_examples = [_baseline_example(row) for row in baseline]
    combined = baseline_examples + new_examples
    conflict_clean, conflicting, conflict_groups = reconcile_example_conflicts(combined)
    quarantine.extend(conflicting)
    conflict_ids = {row.get("example_id") for row in conflicting}
    accepted = [row for row in conflict_clean if row.get("evidence_tier") in {"A", "B", "C"} and row.get("proposed_class_id")]
    for row in accepted:
        issue = validate_mapping(row, canonical_ids)
        if issue:
            quarantine.append({**row, "validation_status": "quarantined_invalid_mapping", "quarantine_reason": issue})
    quarantine_ids = {row.get("example_id") for row in quarantine}
    accepted = [row for row in accepted if row.get("example_id") not in quarantine_ids]

    candidate_pool = conflict_clean + quarantine
    ids = [r.get("example_id", "") for r in candidate_pool]
    duplicate_ids = {cid for cid, count in Counter(ids).items() if cid and count > 1}
    duplicate_example_id_count = sum(count - 1 for cid, count in Counter(ids).items() if cid and count > 1)
    if duplicate_ids:
        duplicates = [r for r in candidate_pool if r.get("example_id") in duplicate_ids]
        quarantine.extend({**r, "validation_status": "quarantined_duplicate_example_id", "quarantine_reason": "duplicate stable source/example identifier"} for r in duplicates)
        candidate_pool = [r for r in candidate_pool if r.get("example_id") not in duplicate_ids]
        candidate_pool.extend(quarantine)
        duplicate_set = {r.get("example_id") for r in quarantine}
        accepted = [r for r in accepted if r.get("example_id") not in duplicate_set]

    vocabulary = []
    for item in taxonomy:
        base = {
            "vocabulary_id": item.class_id, "term": item.canonical_name, "normalized_term": normalize_candidate(item.canonical_name),
            "entry_kind": "canonical_class", "class_id": item.class_id, "canonical_name": item.canonical_name,
            "taxonomy_type": item.type, "discovery_category": "", "evidence_tier": "", "relationship": "canonical",
            "evidence_source_id": "", "evidence_url": "", "evidence_summary": "Existing class preserved unchanged; current taxonomy entry remains scientifically unverified.",
            "evidence_limitations": item.description, "taxonomy_verification_status": item.verification_status,
            "review_status": "not_human_reviewed", "integration_status": "existing_taxonomy_only",
            "source_candidate_ids": "", "source_occurrence_count": "",
        }
        vocabulary.append(base)
        for alias in item.aliases:
            vocabulary.append({**base, "vocabulary_id": f"{item.class_id}:TAXONOMY_ALIAS:{normalize_candidate(alias)}",
                "term": alias, "normalized_term": normalize_candidate(alias), "entry_kind": "taxonomy_declared_alias", "relationship": "taxonomy_declared_alias"})

    source_counts = Counter(normalize_candidate(r.get("normalized_text") or r.get("ingredient_text", "")) for r in source_rows)
    provisional_ids: set[str] = set()
    for key, decision in decisions.items():
        if decision["tier"] not in {"A", "B"}:
            continue
        cid = decision["class_id"]
        inv = inventory_by_phrase[key]
        rule = decision.get("rule", {})
        if cid.startswith("PV-"):
            raise ValueError("invalid provisional ID prefix")
        if cid.startswith("PVA-"):
            provisional_ids.add(cid)
            concept = _vocab_row(cid, decision["canonical_name"], decision, inv, source_counts[key], rule, rule.get("entry_kind", "authority_supported_provisional_concept"))
            concept["vocabulary_id"] = cid
            vocabulary.append(concept)
            if normalize_candidate(decision["canonical_name"]) != key:
                alias = _vocab_row(cid, inv.get("candidate_phrase", key), decision, inv, source_counts[key], rule, "authority_supported_alias")
                alias["vocabulary_id"] = f"{cid}:ALIAS:{key}"
                vocabulary.append(alias)
        elif cid.startswith("PVB-"):
            provisional_ids.add(cid)
            vocabulary.append(_vocab_row(cid, inv.get("candidate_phrase", key), decision, inv, source_counts[key], {}, "source_observed_provisional_concept"))

    output_dir.mkdir(parents=True)
    candidate_pool.sort(key=lambda r: (r.get("source_type", ""), r.get("example_id", ""), r.get("original_text", "")))
    accepted.sort(key=lambda r: (r.get("source_type", ""), r.get("example_id", "")))
    unresolved.sort(key=lambda r: (r.get("candidate_id", ""), r.get("normalized_phrase", "")))
    write_csv(output_dir / "expanded_vocabulary.csv", vocabulary, VOCAB_FIELDS)
    write_csv(output_dir / "candidate_examples.csv", candidate_pool, EXAMPLE_FIELDS)
    write_csv(output_dir / "accepted_automatic_examples.csv", accepted, EXAMPLE_FIELDS)
    write_csv(output_dir / "quarantined_examples.csv", quarantine, QUARANTINE_FIELDS)
    write_csv(output_dir / "unresolved_candidates.csv", unresolved, UNRESOLVED_FIELDS)

    tier_phrase_counts = Counter(d["tier"] for d in decisions.values())
    accepted_tier_counts = Counter(r.get("evidence_tier", "") for r in accepted)
    unique_norms = {normalize_candidate(r.get("normalized_text", "")) for r in accepted}
    semantic_forms = {r.get("semantic_form") or r.get("proposed_class_id") for r in accepted if r.get("semantic_form") or r.get("proposed_class_id")}
    covered_canonical = {r["proposed_class_id"] for r in accepted if r.get("proposed_class_id", "").startswith("FL-")}
    baseline_count = Counter("synthetic" if str(r.get("is_synthetic", "")).casefold() == "true" else "source_derived" for r in baseline)
    accepted_count = Counter(r.get("source_type", "") for r in accepted)
    provisional_category_counts = Counter(
        inventory_by_phrase[key].get("discovery_category", "")
        for key, decision in decisions.items()
        if decision["tier"] in {"A", "B"} and decision["class_id"] not in canonical_ids
    )
    input_paths = [
        phase2_dir / "unmatched_candidates.csv", phase4b_dir / "ingredients_all.csv",
        phase4b_dir / "ingredients_train.csv", phase4b_dir / "ingredients_validation.csv",
        phase4b_dir / "ingredients_test.csv",
        phase6b1_dir / "vocabulary_candidates.csv", phase6b2_dir / "priority_shortlist.csv",
        phase6b2_dir / "candidate_evidence_registry.csv", phase6b4_dir / "pilot_evidence_registry.csv",
        Path(__file__).with_name("taxonomy.py"),
    ]
    report = {
        "pipeline_version": VERSION, "canonical_class_count_before": len(taxonomy), "canonical_class_count_after": len(taxonomy),
        "canonical_class_ids_unchanged": True, "taxonomy_structural_validation": taxonomy_report,
        "vocabulary_inventory_unique_phrases": len(inventory), "source_occurrence_count_unmatched": len(source_rows),
        "source_duplicate_phrase_occurrences": len(source_rows) - len(inventory),
        "unmatched_inventory_frequency_reconciles": sum(int(r.get("frequency") or 0) for r in inventory) == len(source_rows),
        "phase6b2_shortlist_count": len(shortlist), "vocabulary_terms_before": len(taxonomy), "vocabulary_terms_after": len(vocabulary),
        "provisional_concepts_added": len(provisional_ids), "expanded_vocabulary_class_count": len(canonical_ids) + len(provisional_ids),
        "provisional_ingredient_candidate_concepts": provisional_category_counts.get("possible_new_ingredient", 0),
        "provisional_additive_candidate_concepts": provisional_category_counts.get("possible_additive", 0),
        "provisional_compound_candidate_concepts": provisional_category_counts.get("compound_ingredient_expression", 0),
        "provisional_other_category_concepts": len(provisional_ids) - sum(provisional_category_counts.values()),
        "tier_A_identity_supported_candidate_phrases": tier_phrase_counts.get("A", 0),
        "tier_B_source_observed_candidate_phrases": tier_phrase_counts.get("B", 0),
        "tier_D_unresolved_candidate_phrases": tier_phrase_counts.get("D", 0),
        "source_occurrence_tier_counts": dict(sorted(occurrence_tiers.items())),
        "accepted_automatic_example_count": len(accepted), "candidate_example_count": len(candidate_pool),
        "quarantined_example_count": len(quarantine), "unresolved_candidate_count": len(unresolved),
        "duplicate_example_id_count": duplicate_example_id_count,
        "accepted_unique_normalized_phrases": len(unique_norms), "accepted_unique_semantic_forms": len(semantic_forms),
        "accepted_evidence_tier_example_counts": dict(sorted(accepted_tier_counts.items())),
        "baseline_example_count": len(baseline), "baseline_source_derived_count": baseline_count.get("source_derived", 0),
        "baseline_synthetic_count": baseline_count.get("synthetic", 0),
        "accepted_source_derived_count": accepted_count.get("source_derived", 0), "accepted_synthetic_count": accepted_count.get("synthetic", 0),
        "new_source_derived_accepted_count": accepted_count.get("source_derived", 0) - baseline_count.get("source_derived", 0),
        "independently_supported_identity_mapping_example_count": sum(r.get("evidence_tier") == "A" for r in accepted),
        "tier_A_existing_canonical_mapping_example_count": sum(r.get("evidence_tier") == "A" and r.get("proposed_class_id", "").startswith("FL-") for r in accepted),
        "examples_requiring_human_review_count": len(accepted), "canonical_class_coverage_count": len(covered_canonical),
        "canonical_class_coverage_total": len(canonical_ids), "canonical_class_coverage_fraction": len(covered_canonical) / max(len(canonical_ids), 1),
        "human_reviewed_example_count": 0, "task02_human_review_target": 3000, "task02_target_met": False,
        "conflicting_normalized_label_groups": conflict_groups, "unmatched_rows_missing_discovery_record": missing_inventory_count,
        "unsupported_e_number_phrases": sum("E-number-like" in r["unresolved_reason"] for r in unresolved),
        "no_human_review_claims": all(r.get("review_status") == "not_human_reviewed" for r in accepted + candidate_pool),
        "baseline_dataset_modified": False, "taxonomy_modified": False, "allergen_processing_performed": False, "model_training_performed": False,
        "input_sha256": {str(p): sha256_file(p) for p in input_paths if p.exists()},
        "limitations": [
            "Current taxonomy classes remain scientifically unverified; exact automated matches do not upgrade verification status.",
            "Tier A authority-backed identity does not constitute human review, ground truth, or blanket use authorization.",
            "Tier B terms receive separate provisional IDs; semantic synonyms and product-level independence are not inferred.",
            "Tier C reuses existing controlled variants only; Phase 7A creates no new synthetic variants.",
            "Source data lacks reliable product IDs, so product-level independence cannot be claimed.",
            "The 3,000-example goal is for human-reviewed examples and is not met by this automatic expansion.",
        ],
    }
    tier_report = {
        "tier_candidate_phrase_counts": dict(sorted(tier_phrase_counts.items())),
        "tier_source_occurrence_counts": dict(sorted(occurrence_tiers.items())),
        "tier_accepted_example_counts": dict(sorted(accepted_tier_counts.items())),
        "definitions": {
            "A": "Authoritative reference explicitly supports this exact identity or synonym relation; not human reviewed.",
            "B": "Source-observed provisional term passing conservative structure checks; identity remains unverified.",
            "C": "Existing controlled synthetic taxonomy surface variant; not source-observed.",
            "D": "Unresolved or unsuitable for automatic mapping.",
        },
    }
    (output_dir / "evidence_tier_report.json").write_text(json.dumps(tier_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "vocabulary_expansion_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "vocabulary_expansion_report.md").write_text(_report_markdown(report), encoding="utf-8")
    return report


def _report_markdown(report: dict) -> str:
    return (
        "# FoodLence V4 Phase 7A vocabulary expansion\n\n"
        f"- Existing canonical classes: {report['canonical_class_count_before']} (unchanged)\n"
        f"- Vocabulary entries before / after: {report['vocabulary_terms_before']} / {report['vocabulary_terms_after']}\n"
        f"- Provisional concepts added: {report['provisional_concepts_added']}\n"
        f"- Ingredient / additive provisional concepts: {report['provisional_ingredient_candidate_concepts']} / {report['provisional_additive_candidate_concepts']}\n"
        f"- Compound-expression provisional concepts: {report['provisional_compound_candidate_concepts']}\n"
        f"- Other heuristic-category provisional concepts: {report['provisional_other_category_concepts']}\n"
        f"- Automatically accepted examples: {report['accepted_automatic_example_count']}\n"
        f"- Candidate example pool: {report['candidate_example_count']}\n"
        f"- Accepted source occurrences by tier: {json.dumps(report['source_occurrence_tier_counts'], sort_keys=True)}\n"
        f"- Unique normalized phrases / semantic forms in accepted pool: {report['accepted_unique_normalized_phrases']} / {report['accepted_unique_semantic_forms']}\n"
        f"- Source-derived / synthetic accepted examples: {report['accepted_source_derived_count']} / {report['accepted_synthetic_count']}\n"
        f"- Unresolved phrases / quarantined examples: {report['unresolved_candidate_count']} / {report['quarantined_example_count']}\n"
        f"- Existing canonical coverage: {report['canonical_class_coverage_count']} / {report['canonical_class_coverage_total']}\n\n"
        "All examples remain not_human_reviewed. Evidence tiers describe evidence and processing provenance; they do not establish ground truth. "
        "The 3,000 human-reviewed example target remains unmet.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).parents[1] / "foodlence_generated_v4"
    parser.add_argument("--phase2-dir", type=Path, default=root / "phase2")
    parser.add_argument("--phase4b-dir", type=Path, default=root / "phase4b_corrected")
    parser.add_argument("--phase6b1-dir", type=Path, default=root / "phase6b1")
    parser.add_argument("--phase6b2-dir", type=Path, default=root / "phase6b2")
    parser.add_argument("--phase6b4-dir", type=Path, default=root / "phase6b4")
    parser.add_argument("--output-dir", type=Path, default=root / "phase7a")
    args = parser.parse_args()
    report = expand_vocabulary(args.phase2_dir, args.phase4b_dir, args.phase6b1_dir, args.phase6b2_dir, args.phase6b4_dir, args.output_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

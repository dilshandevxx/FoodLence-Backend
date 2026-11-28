"""Rank Phase 6B-1 vocabulary candidates and prepare evidence/review records.

Priority scores are workflow triage scores, not ingredient confidence.
No taxonomy or training data is written by this module.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .taxonomy import TAXONOMY

DEFAULT_LIMIT = 500
DEFAULT_STANDALONE_LIMIT = 300
DEFAULT_ADDITIVE_LIMIT = 150
DEFAULT_INVESTIGATION_LIMIT = 50
DEFAULT_COMPOUND_LIMIT = 25
EVIDENCE_CHECK_DATE = "2026-11-23"

# Candidate-specific references were checked against FDA Human Foods Program
# entries. These are evidence leads, not endorsements, class activations, or
# completed human review. Candidate text keys must match the reviewed phrase.
AUTHORITATIVE_EVIDENCE = {
    "food starch modified": {
        "status": "evidence_found", "source_id": "FDA-FS-STARCHFOODMODIFIED",
        "source_title": "FDA Substances Added to Food: STARCH, FOOD, MODIFIED",
        "source_url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=STARCHFOODMODIFIED&set=FoodSubstances",
        "terminology": "STARCH, FOOD, MODIFIED; other name FOOD STARCH, MODIFIED; 21 CFR 172.892",
        "relationship": "FDA recognizes a food-starch-modified additive term. Candidate punctuation/order is close to the listed term; this supports terminology review, not equivalence to any source-specific modified starch.",
        "proposed_additive": True,
        "proposed_existing_class_id": "", "proposed_existing_class_name": "", "proposed_new_concept": "food starch, modified",
        "ambiguity": "A broad modified starch term is not interchangeable with modified corn starch or another source-specific starch.",
    },
    "agar agar": {
        "status": "evidence_found", "source_id": "FDA-FS-AGAR",
        "source_title": "FDA Substances Added to Food: AGAR (GELIDIUM SPP.)",
        "source_url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=AGAR&set=FoodSubstances",
        "terminology": "AGAR-AGAR listed among other names for AGAR (GELIDIUM SPP.); 21 CFR 184.1115",
        "relationship": "The FDA entry supports agar-agar as listed terminology for agar. The taxonomy has no agar class; this is a proposed new additive/ingredient concept for review only.",
        "proposed_additive": True,
        "proposed_existing_class_id": "", "proposed_existing_class_name": "", "proposed_new_concept": "agar",
        "ambiguity": "The FDA record specifies Gelidium spp.; the source phrase alone does not establish species/source identity.",
    },
    "baking soda": {
        "status": "evidence_found", "source_id": "FDA-FS-SODIUMBICARBONATE",
        "source_title": "FDA Substances Added to Food: SODIUM BICARBONATE",
        "source_url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=SODIUMBICARBONATE&set=FoodSubstances",
        "terminology": "BAKING SODA (SODIUM BICARBONATE); 21 CFR 184.1736",
        "relationship": "FDA lists baking soda as another name for sodium bicarbonate. Proposed mapping targets the existing canonical class but is not activated and still needs human review in the project context.",
        "proposed_additive": True,
        "proposed_existing_class_id": "FL-160", "proposed_existing_class_name": "sodium bicarbonate", "proposed_new_concept": "",
        "ambiguity": "Confirm that the source phrase denotes the pure substance rather than a baking-powder mixture or product description.",
    },
    "mono diglycerides": {
        "status": "insufficient_evidence", "source_id": "FDA-FS-MONOANDDIGLYCERIDES",
        "source_title": "FDA Substances Added to Food: MONO- AND DIGLYCERIDES",
        "source_url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=MONOANDDIGLYCERIDES&set=FoodSubstances",
        "terminology": "FDA record uses MONO- AND DIGLYCERIDES and lists related other names; it does not exactly establish the source phrase without 'and'.",
        "relationship": "Related official terminology was found, but equivalence of this source phrase was not established.",
        "proposed_existing_class_id": "", "proposed_existing_class_name": "", "proposed_new_concept": "",
        "ambiguity": "The source phrase may be shorthand or an OCR/text-normalization loss; do not activate a synonym without review.",
    },
    "mono and diglycerides": {
        "status": "evidence_found", "source_id": "FDA-FS-MONOANDDIGLYCERIDES",
        "source_title": "FDA Substances Added to Food: MONO- AND DIGLYCERIDES",
        "source_url": "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=MONOANDDIGLYCERIDES&set=FoodSubstances",
        "terminology": "MONO- AND DIGLYCERIDES; FDA lists 21 CFR 172.812, 175.105, and 184.1505 and several technical effects including emulsifier and stabilizer",
        "relationship": "The FDA record uses the same ingredient expression and identifies its regulatory listing and technical effects. The evidence supports terminology/category investigation, not an activated taxonomy class or label for a particular product.",
        "proposed_additive": True, "proposed_existing_class_id": "", "proposed_existing_class_name": "", "proposed_new_concept": "",
        "ambiguity": "The grouped name covers a glyceride mixture; do not split into or merge with a chemically distinct glyceride without suitable evidence.",
    },
}

DISCOVERY_FIELDS = [
    "candidate_phrase", "normalized_phrase", "frequency", "source_references", "discovery_category",
    "suggested_existing_class_id", "suggested_existing_class_name", "suggested_new_class_name",
    "candidate_evidence", "evidence_source", "verification_status", "review_status", "priority_score",
    "priority_rationale", "character_count", "word_count", "pattern_flags",
]
SHORTLIST_FIELDS = [
    "candidate_id", "candidate_phrase", "normalized_phrase", "discovery_category", "discovery_status", "source_occurrence_count",
    "proposed_relationship", "proposed_existing_class_id", "proposed_existing_class_name", "proposed_new_concept",
    "priority_score", "priority_components", "family_key", "evidence_status", "review_status", "integration_status",
    "integration_eligibility", "source_reference_registry_key",
]
REVIEW_FIELDS = [
    "candidate_id", "candidate_phrase", "normalized_phrase", "discovery_category", "discovery_status", "source_occurrence_count",
    "source_reference_sample", "source_reference_count", "source_reference_registry_key", "proposed_relationship",
    "proposed_existing_class_id", "proposed_existing_class_name", "proposed_new_concept", "evidence_source_ids",
    "evidence_urls", "evidence_summary", "ambiguity_notes", "priority_score", "evidence_status", "review_status",
    "reviewer_decision", "reviewer_identifier", "review_timestamp", "review_justification", "integration_status",
    "integration_eligibility",
]


def candidate_id(normalized_phrase: str) -> str:
    digest = hashlib.sha256(("foodlence-v4-vocabulary-v1\0" + normalized_phrase).encode("utf-8")).hexdigest()[:20]
    return "VOC-" + digest.upper()


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        required = set(DISCOVERY_FIELDS)
        if not required.issubset(fields):
            raise ValueError(f"discovery CSV missing required fields: {sorted(required - set(fields))}")
        rows = list(reader)
    return rows, fields


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _family_key(phrase: str) -> str:
    ignored = {"organic", "natural", "artificial", "dried", "fresh", "raw", "whole", "modified", "partially", "pasteurized", "pasteurised", "refined", "roasted", "ground", "powdered", "concentrated", "low", "fat", "free", "food", "and", "or", "the", "of", "with"}
    tokens = re.findall(r"[a-z0-9]+", phrase.casefold())
    meaningful = [token for token in tokens if token not in ignored]
    return meaningful[0] if meaningful else (tokens[0] if tokens else "empty")


def _evidence(phrase: str) -> dict:
    if phrase in AUTHORITATIVE_EVIDENCE:
        return dict(AUTHORITATIVE_EVIDENCE[phrase])
    return {
        "status": "not_checked", "source_id": "", "source_title": "", "source_url": "", "terminology": "",
        "relationship": "No candidate-specific authoritative evidence was recorded in this phase.",
        "proposed_existing_class_id": "", "proposed_existing_class_name": "", "proposed_new_concept": "",
        "ambiguity": "Requires source-aware human interpretation; no mapping inferred.",
    }


def score_candidate(row: dict, evidence: dict, canonical_names: set[str], train_counts: dict[str, int]) -> tuple[int, dict[str, int]]:
    """0-100 review score. Formula terms are explicit and deterministic.

    +0..20 source frequency: min(20, round(5*log2(n+1)))
    +0..25 candidate type plausibility; +0..25 exact authoritative evidence;
    +0..15 lexical distinction from canonical terms; +0..10 an evidenced
    underrepresented target class. Subtract complexity/ambiguity/noise penalties.
    The result is sorting priority only, not scientific confidence.
    """
    phrase = row["normalized_phrase"]
    frequency = int(row["frequency"])
    category = row["discovery_category"]
    frequency_points = min(20, round(5 * math.log2(frequency + 1)))
    plausibility = {"possible_new_ingredient": 25, "possible_additive": 23, "possible_existing_class_alias": 20, "compound_ingredient_expression": 7, "ambiguous": 4, "product_or_description": 0, "invalid_or_noise": 0}.get(category, 0)
    evidence_points = 25 if evidence["status"] == "evidence_found" else 8 if evidence["status"] == "insufficient_evidence" else 0
    distinctness = 15 if phrase not in canonical_names else 0
    class_id = evidence.get("proposed_existing_class_id") or row.get("suggested_existing_class_id", "")
    representation = 10 if class_id and train_counts.get(class_id, 0) < 2 else 0
    flags = set((row.get("pattern_flags") or "").split(";"))
    complexity = 0
    if int(row.get("word_count") or 0) > 4:
        complexity += 5
    if int(row.get("character_count") or 0) > 80:
        complexity += 5
    if flags & {"numeric_or_code_like", "e_number_like_pattern", "unbalanced_delimiter", "alias_collision"}:
        complexity += 5
    risk = 15 if category == "ambiguous" else 20 if category == "compound_ingredient_expression" else 25 if category in {"product_or_description", "invalid_or_noise"} else 0
    parts = {"frequency": frequency_points, "candidate_type": plausibility, "authoritative_evidence": evidence_points, "canonical_distinctness": distinctness, "underrepresented_class": representation, "complexity_penalty": -complexity, "ambiguity_noise_penalty": -risk}
    return max(0, min(100, sum(parts.values()))), parts


def _compact_fingerprint(phrase: str) -> str:
    """Suppress only exact punctuation/spacing variants; never infer synonyms."""
    return re.sub(r"[^a-z0-9]", "", phrase.casefold())


def _choose(rows: list[dict], limit: int, per_family: int, canonical_names: set[str], train_counts: dict[str, int], occupied_fingerprints: set[str], category_cap: int | None = None, minimum_score: int = 20) -> list[dict]:
    scored = []
    for row in rows:
        ev = _evidence(row["normalized_phrase"])
        score, parts = score_candidate(row, ev, canonical_names, train_counts)
        scored.append((score, int(row["frequency"]), row["normalized_phrase"], row, ev, parts))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    chosen = []
    families = Counter()
    max_count = min(limit, category_cap if category_cap is not None else limit)
    for score, frequency, phrase, row, ev, parts in scored:
        if len(chosen) >= max_count:
            break
        # Candidate quality gates: frequency cannot rescue descriptions, noise,
        # ambiguous terms, or compound expressions into standalone buckets.
        if score < minimum_score or row["discovery_category"] in {"invalid_or_noise", "product_or_description"}:
            continue
        fingerprint = _compact_fingerprint(phrase)
        if not fingerprint or fingerprint in occupied_fingerprints:
            continue
        family = _family_key(phrase)
        if families[family] >= per_family:
            continue
        occupied_fingerprints.add(fingerprint)
        families[family] += 1
        chosen.append({**row, "candidate_id": candidate_id(phrase), "priority_score": score, "priority_components": json.dumps(parts, sort_keys=True, separators=(",", ":")), "family_key": family, "evidence": ev})
    return chosen


def _proposal(row: dict, evidence: dict) -> tuple[str, str, str]:
    if evidence.get("proposed_existing_class_id"):
        return "proposed synonym/name relationship to existing canonical class", evidence["proposed_existing_class_id"], evidence["proposed_existing_class_name"]
    if evidence.get("proposed_new_concept"):
        return "potential new/additive concept; evidence supports terminology only", "", ""
    category = row["discovery_category"]
    if category == "compound_ingredient_expression":
        return "compound expression; investigate components before any class proposal", "", ""
    if category == "possible_additive":
        return "possible additive term; identity and regulatory status require review", "", ""
    if category == "possible_new_ingredient":
        return "possible distinct ingredient concept; identity unverified", "", ""
    if category == "possible_existing_class_alias":
        return "possible existing-class alias; requires evidence review", "", ""
    return "unresolved; human interpretation required", "", ""


def prioritize_vocabulary(discovery_path: Path, output_dir: Path, class_distribution_path: Path | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing prioritization output: {output_dir}")
    if limit < 0:
        raise ValueError("limit must be non-negative")
    rows, _ = _read_csv(discovery_path)
    for row in rows:
        if not row.get("normalized_phrase"):
            raise ValueError("discovery candidates require normalized_phrase")
    if len({r["normalized_phrase"] for r in rows}) != len(rows):
        raise ValueError("discovery inventory contains duplicate normalized phrases")
    taxonomy_rows = TAXONOMY
    canonical_names = {x.canonical_name.casefold() for x in taxonomy_rows} | {a.casefold() for x in taxonomy_rows for a in x.aliases}
    class_by_name = {x.canonical_name.casefold(): x for x in taxonomy_rows}
    # Validate the evidence-backed class proposal against the current taxonomy.
    for value in AUTHORITATIVE_EVIDENCE.values():
        cid = value.get("proposed_existing_class_id")
        name = value.get("proposed_existing_class_name")
        if cid and (cid not in {x.class_id for x in taxonomy_rows} or class_by_name.get(name.casefold(), None) is None or class_by_name[name.casefold()].class_id != cid):
            raise ValueError(f"evidence proposal references an invalid taxonomy class: {cid} {name}")
    train_counts = {}
    if class_distribution_path and class_distribution_path.exists():
        with class_distribution_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                train_counts[row.get("canonical_class_id", "")] = int(row.get("train_examples") or 0)

    inventory = {row["normalized_phrase"]: row for row in rows}
    selected: list[dict] = []
    fingerprints: set[str] = set()
    remaining_limit = limit
    standalone = _choose([r for r in rows if r["discovery_category"] == "possible_new_ingredient"], min(DEFAULT_STANDALONE_LIMIT, remaining_limit), 8, canonical_names, train_counts, fingerprints)
    selected.extend(standalone); remaining_limit -= len(standalone)
    additives = _choose([r for r in rows if r["discovery_category"] == "possible_additive"], min(DEFAULT_ADDITIVE_LIMIT, remaining_limit), 8, canonical_names, train_counts, fingerprints)
    selected.extend(additives); remaining_limit -= len(additives)

    # Reserve at most half of the final investigation allocation for compounds;
    # keep a separate share for ambiguous/alias terms. No weak candidates are
    # admitted solely to fill either cap.
    investigation_cap = min(DEFAULT_INVESTIGATION_LIMIT, remaining_limit)
    compound_cap = min(DEFAULT_COMPOUND_LIMIT, (investigation_cap + 1) // 2)
    compounds = _choose([r for r in rows if r["discovery_category"] == "compound_ingredient_expression"], compound_cap, 4, canonical_names, train_counts, fingerprints, minimum_score=15)
    selected.extend(compounds); remaining_limit -= len(compounds)
    uncertain_cap = min(investigation_cap - len(compounds), remaining_limit)
    uncertain_rows = [r for r in rows if r["discovery_category"] in {"ambiguous", "possible_existing_class_alias"}]
    uncertain = _choose(uncertain_rows, uncertain_cap, 3, canonical_names, train_counts, fingerprints)
    selected.extend(uncertain)
    selected.sort(key=lambda r: (-r["priority_score"], -int(r["frequency"]), r["normalized_phrase"]))
    selected_phrases = {r["normalized_phrase"] for r in selected}

    # Ensure named complex terms from the Phase 6B-2 investigation prompt are
    # visible in the compound queue if they independently qualified for the
    # shortlist; they are never decomposed or mapped here.
    compound_examples = {"glucose fructose syrup", "pasteurized part skim milk", "food starch modified"}
    shortlist_records = []
    evidence_records = []
    mappings = []
    concepts = []
    additive_records = []
    compound_queue = []
    review_rows = []
    for selected_row in selected:
        phrase = selected_row["normalized_phrase"]
        ev = selected_row["evidence"]
        relationship, proposed_id, proposed_name = _proposal(selected_row, ev)
        discovery_status = "ambiguous" if selected_row["discovery_category"] in {"ambiguous", "compound_ingredient_expression"} else "candidate"
        integration_eligibility = "eligible_after_review" if ev["status"] == "evidence_found" else "not_eligible_pending_evidence_and_review"
        if selected_row["discovery_category"] in {"ambiguous", "compound_ingredient_expression"}:
            integration_eligibility = "not_eligible_pending_interpretation_and_review"
        refs = json.loads(selected_row["source_references"])
        evidence_summary = ev["relationship"]
        all_refs = selected_row["source_references"]
        shortlist_records.append({
            "candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
            "discovery_category": selected_row["discovery_category"], "discovery_status": discovery_status, "source_occurrence_count": selected_row["frequency"],
            "proposed_relationship": relationship, "proposed_existing_class_id": proposed_id, "proposed_existing_class_name": proposed_name,
            "proposed_new_concept": ev.get("proposed_new_concept", ""), "priority_score": selected_row["priority_score"],
            "priority_components": selected_row["priority_components"], "family_key": selected_row["family_key"],
            "evidence_status": ev["status"], "review_status": "not_human_reviewed", "integration_status": "not_integrated",
            "integration_eligibility": integration_eligibility, "source_reference_registry_key": selected_row["candidate_id"],
        })
        evidence_records.append({
            "candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
            "discovery_category": selected_row["discovery_category"], "discovery_status": discovery_status, "source_occurrence_count": selected_row["frequency"],
            "original_source_references": all_refs, "source_reference_count": len(refs),
            "proposed_relationship": relationship, "proposed_existing_class_id": proposed_id, "proposed_existing_class_name": proposed_name,
            "proposed_new_concept": ev.get("proposed_new_concept", ""), "evidence_source_id": ev.get("source_id", ""),
            "evidence_source_title": ev.get("source_title", ""), "evidence_url": ev.get("source_url", ""),
            "evidence_checked_date": EVIDENCE_CHECK_DATE if ev.get("source_id") else "",
            "relevant_terminology": ev.get("terminology", ""), "evidence_summary": evidence_summary,
            "ambiguity_notes": ev.get("ambiguity", ""), "priority_score": selected_row["priority_score"],
            "evidence_status": ev["status"], "review_status": "not_human_reviewed", "integration_status": "not_integrated",
        })
        if proposed_id:
            mappings.append({"candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
                             "proposed_canonical_class_id": proposed_id, "proposed_canonical_name": proposed_name,
                             "proposal_basis": ev.get("terminology", ""), "evidence_source_id": ev.get("source_id", ""), "evidence_url": ev.get("source_url", ""),
                             "evidence_status": ev["status"], "review_status": "not_human_reviewed", "integration_status": "not_integrated"})
        if (selected_row["discovery_category"] == "possible_new_ingredient" and not proposed_id) or ev.get("proposed_new_concept"):
            concepts.append({"candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
                             "proposed_concept_name": ev.get("proposed_new_concept") or phrase, "concept_type": "possible additive" if ev.get("proposed_new_concept") in {"agar", "food starch, modified"} else "possible ingredient",
                             "proposal_basis": relationship, "evidence_source_id": ev.get("source_id", ""), "evidence_url": ev.get("source_url", ""),
                             "evidence_status": ev["status"], "priority_score": selected_row["priority_score"], "review_status": "not_human_reviewed", "integration_status": "not_integrated"})
        if selected_row["discovery_category"] == "possible_additive" or ev.get("proposed_additive"):
            additive_records.append({"candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
                                    "discovery_category": selected_row["discovery_category"], "source_occurrence_count": selected_row["frequency"],
                                    "evidence_source_id": ev.get("source_id", ""), "evidence_url": ev.get("source_url", ""),
                                    "evidence_summary": evidence_summary, "evidence_status": ev["status"], "review_status": "not_human_reviewed", "integration_status": "not_integrated"})
        if selected_row["discovery_category"] == "compound_ingredient_expression" or phrase in compound_examples:
            compound_queue.append({"candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
                                   "source_occurrence_count": selected_row["frequency"], "investigation_question": "Does this phrase identify one ingredient, a derivative/form, or a compound expression? Do not decompose or map without source-specific evidence.",
                                   "relationship_proposal": relationship, "evidence_status": ev["status"], "review_status": "not_human_reviewed", "integration_status": "not_integrated"})
        ref_sample = [f"{ref.get('source_dataset','')}#{ref.get('source_row_id','')} [{ref.get('candidate_id','')}]" for ref in refs[:3]]
        review_rows.append({
            "candidate_id": selected_row["candidate_id"], "candidate_phrase": selected_row["candidate_phrase"], "normalized_phrase": phrase,
            "discovery_category": selected_row["discovery_category"], "discovery_status": discovery_status, "source_occurrence_count": selected_row["frequency"],
            "source_reference_sample": " | ".join(ref_sample), "source_reference_count": len(refs),
            "source_reference_registry_key": selected_row["candidate_id"], "proposed_relationship": relationship,
            "proposed_existing_class_id": proposed_id, "proposed_existing_class_name": proposed_name,
            "proposed_new_concept": ev.get("proposed_new_concept", ""), "evidence_source_ids": ev.get("source_id", ""),
            "evidence_urls": ev.get("source_url", ""), "evidence_summary": evidence_summary,
            "ambiguity_notes": ev.get("ambiguity", ""), "priority_score": selected_row["priority_score"],
            "evidence_status": ev["status"], "review_status": "pending_human_review",
            "reviewer_decision": "", "reviewer_identifier": "", "review_timestamp": "", "review_justification": "",
            "integration_status": "not_integrated", "integration_eligibility": integration_eligibility,
        })

    deferred_rows = []
    for row in rows:
        if row["normalized_phrase"] in selected_phrases:
            continue
        ev = _evidence(row["normalized_phrase"])
        score, parts = score_candidate(row, ev, canonical_names, train_counts)
        deferred_rows.append({"candidate_id": candidate_id(row["normalized_phrase"]), "candidate_phrase": row["candidate_phrase"],
                              "normalized_phrase": row["normalized_phrase"], "discovery_category": row["discovery_category"],
                              "discovery_status": "ambiguous" if row["discovery_category"] in {"ambiguous", "compound_ingredient_expression"} else "excluded" if row["discovery_category"] == "invalid_or_noise" else "candidate",
                              "source_occurrence_count": row["frequency"], "priority_score": score,
                              "deferred_reason": "outside shortlist cap or below category/family selection criteria",
                              "source_reference_registry_key": row["normalized_phrase"]})
    deferred_rows.sort(key=lambda row: (-row["priority_score"], -int(row["source_occurrence_count"]), row["normalized_phrase"]))

    output_dir.mkdir(parents=True)
    _write(output_dir / "priority_shortlist.csv", shortlist_records, SHORTLIST_FIELDS)
    _write(output_dir / "candidate_evidence_registry.csv", evidence_records, list(evidence_records[0]) if evidence_records else ["candidate_id", "candidate_phrase", "normalized_phrase", "original_source_references", "evidence_status", "review_status", "integration_status"])
    _write(output_dir / "proposed_existing_class_mappings.csv", mappings, ["candidate_id", "candidate_phrase", "normalized_phrase", "proposed_canonical_class_id", "proposed_canonical_name", "proposal_basis", "evidence_source_id", "evidence_url", "evidence_status", "review_status", "integration_status"])
    concept_fields = ["candidate_id", "candidate_phrase", "normalized_phrase", "proposed_concept_name", "concept_type", "proposal_basis", "evidence_source_id", "evidence_url", "evidence_status", "priority_score", "review_status", "integration_status"]
    _write(output_dir / "proposed_new_ingredient_concepts.csv", concepts, concept_fields)
    additive_fields = ["candidate_id", "candidate_phrase", "normalized_phrase", "discovery_category", "source_occurrence_count", "evidence_source_id", "evidence_url", "evidence_summary", "evidence_status", "review_status", "integration_status"]
    _write(output_dir / "proposed_additive_candidates.csv", additive_records, additive_fields)
    compound_fields = ["candidate_id", "candidate_phrase", "normalized_phrase", "source_occurrence_count", "investigation_question", "relationship_proposal", "evidence_status", "review_status", "integration_status"]
    _write(output_dir / "compound_investigation_queue.csv", compound_queue, compound_fields)
    _write(output_dir / "human_review_template.csv", review_rows, REVIEW_FIELDS)
    deferred_fields = ["candidate_id", "candidate_phrase", "normalized_phrase", "discovery_category", "discovery_status", "source_occurrence_count", "priority_score", "deferred_reason", "source_reference_registry_key"]
    _write(output_dir / "deferred_candidates.csv", deferred_rows, deferred_fields)

    category_counts = Counter(row["discovery_category"] for row in selected)
    deferred_category_counts = Counter(row["discovery_category"] for row in rows if row["normalized_phrase"] not in selected_phrases)
    evidence_counts = Counter(row["evidence"]["status"] for row in selected)
    report = {
        "pipeline_version": "FoodLence V4 Phase 6B-2", "discovery_inventory_rows": len(rows),
        "discovery_inventory_sha256": hashlib.sha256(discovery_path.read_bytes()).hexdigest(),
        "shortlist_limit": limit, "shortlist_count": len(selected), "deferred_count": len(deferred_rows),
        "shortlist_and_deferred_reconcile": len(selected) + len(deferred_rows) == len(rows),
        "selected_counts_by_discovery_category": dict(sorted(category_counts.items())),
        "deferred_counts_by_discovery_category": dict(sorted(deferred_category_counts.items())),
        "allocation_caps": {"standalone_food_candidates": DEFAULT_STANDALONE_LIMIT, "additive_candidates": DEFAULT_ADDITIVE_LIMIT, "ambiguous_or_existing_class_candidates": DEFAULT_INVESTIGATION_LIMIT, "compound_share_of_investigation_cap": DEFAULT_COMPOUND_LIMIT},
        "selected_allocation_counts": {"standalone_food_candidates": len(standalone), "additive_candidates": len(additives), "compound_investigation_candidates": len(compounds), "ambiguous_or_existing_class_candidates": len(uncertain)},
        "proposed_existing_class_mapping_count": len(mappings), "proposed_new_concept_count": len(concepts),
        "proposed_additive_candidate_count": len(additive_records), "compound_investigation_queue_count": len(compound_queue),
        "discovered_compound_expression_count": sum(r["discovery_category"] == "compound_ingredient_expression" for r in rows),
        "shortlisted_compound_expression_count": category_counts["compound_ingredient_expression"],
        "deferred_compound_expression_count": deferred_category_counts["compound_ingredient_expression"],
        "evidence_status_counts": dict(sorted(evidence_counts.items())), "evidence_found_count": evidence_counts["evidence_found"],
        "human_review_template_count": len(review_rows), "human_review_completed_count": 0,
        "review_status": "pending_human_review" if review_rows else "not_human_reviewed",
        "reviewer_decision_fields_blank": all(not any(row[k] for k in ("reviewer_decision", "reviewer_identifier", "review_timestamp", "review_justification")) for row in review_rows),
        "integration_status_counts": {"not_integrated": len(selected)},
        "taxonomy_modified": False, "authoritative_dataset_modified": False, "all_proposals_non_activating": True,
        "ranking_formula": "Score = min(100,max(0, frequency + candidate_type + exact_authoritative_evidence + canonical_distinctness + underrepresented_class - complexity - ambiguity/noise)). Frequency=min(20,round(5*log2(n+1))); candidate type 0-25; exact evidence 25, checked-insufficient 8, unchecked 0; canonical distinction 15 when phrase is not an exact canonical/alias; underrepresented target 10 only when an evidence-backed existing target has <2 training examples; complexity 0-15; ambiguity/noise 0-25. It is a review priority, never scientific confidence.",
        "family_diversity_rule": "One shortlist slot per punctuation/space compact fingerprint; per-family caps are 8 standalone, 8 additive, 4 compounds, and 3 ambiguous/existing-term candidates. Family key is the first token after a documented common descriptor stoplist.",
        "evidence_method": "Candidate-specific authoritative FDA Human Foods Program records were checked for exact candidate terminology where available; other shortlisted phrases remain not_checked. The exact 'mono and diglycerides' term has a supporting FDA record; the phrase without 'and' remains insufficient_evidence. Retrieval date 2026-11-23.",
        "limitations": ["Frequency is not proof of ingredient identity.", "Evidence retrieval does not constitute human review or project-level label approval.", "Proposed mappings are inactive and all shortlisted items remain unintegrated.", "Only exact phrase-specific sources were recorded; no broad synonym matching was applied.", "Deferred candidates retain their complete source references in the unchanged Phase 6B-1 inventory."],
    }
    (output_dir / "prioritization_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(output_dir / "prioritization_report.md", report, selected)
    return report


def _write_markdown(path: Path, report: dict, selected: list[dict]) -> None:
    lines = ["# FoodLence V4 vocabulary prioritization", "", f"- Discovery candidates inspected: {report['discovery_inventory_rows']}",
             f"- Shortlist: {report['shortlist_count']} / {report['shortlist_limit']}", f"- Deferred for later review: {report['deferred_count']}",
             f"- Compound expressions shortlisted / deferred: {report['shortlisted_compound_expression_count']} / {report['deferred_compound_expression_count']}",
             f"- Candidate-specific evidence found: {report['evidence_found_count']}", "- Human review completed: 0", "- Taxonomy/data integration: none", "",
             "## Selected discovery categories", "", "| Category | Count |", "|---|---:|"]
    for category, count in report["selected_counts_by_discovery_category"].items():
        lines.append(f"| {category} | {count} |")
    lines += ["", "## Ranking and safeguards", "", report["ranking_formula"], "", report["family_diversity_rule"], "",
              "The score prioritizes review work; it is not scientific confidence. Candidate evidence records use exact source terminology and URLs where checked. A document mention or database entry does not itself complete human review.",
              "", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path(__file__).parents[1] / "foodlence_generated_v4"
    parser.add_argument("--input", type=Path, default=base / "phase6b1" / "vocabulary_candidates.csv")
    parser.add_argument("--output-dir", type=Path, default=base / "phase6b2")
    parser.add_argument("--class-distribution", type=Path, default=base / "final_reports" / "v4_class_distribution.csv")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="maximum total unique shortlisted candidates (default: 500)")
    args = parser.parse_args()
    print(json.dumps(prioritize_vocabulary(args.input, args.output_dir, args.class_distribution, args.limit), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

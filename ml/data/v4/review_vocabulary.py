"""Prepare reviewer batches and conservatively validate imported decisions.

CSV decisions are claims. Only records independently attested by a separately
configured trusted reviewer can be exported as reviewed decisions; nothing in
this module changes the taxonomy or training data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .discover_vocabulary import normalize_candidate
from .taxonomy import TAXONOMY

DECISIONS = {
    "approve_existing_class_alias", "approve_new_ingredient_concept", "approve_additive_concept",
    "requires_more_evidence", "reject", "defer",
}
EVIDENCE_SUPPORT_TYPES = {"synonym_identity", "ingredient_identity", "distinct_concept", "additive_identity", "regulatory_identity_or_use", "terminology_only"}
RELATIONSHIPS = {"synonym", "common_name", "spelling_variant", "distinct_ingredient", "ingredient_derivative", "distinct_additive"}
DECISION_FIELDS = [
    "candidate_id", "candidate_phrase", "reviewer_decision", "reviewer_identifier", "review_date",
    "reviewer_justification", "reviewed_canonical_class_id", "reviewed_canonical_name", "reviewed_category",
    "relationship_type", "evidence_support_type", "evidence_references",
]
ATTESTATION_FIELDS = ["candidate_id", "review_record_sha256", "attestor_identifier", "attested_at", "attestation_reference"]
REGISTER_FIELDS = [
    "batch_id", "candidate_id", "candidate_phrase", "normalized_phrase", "discovery_category", "discovery_status",
    "source_occurrence_count", "original_source_references", "proposed_ingredient_identity", "proposed_relationship_type",
    "proposed_relationship", "proposed_canonical_class_id", "proposed_canonical_class_name", "proposed_new_concept",
    "evidence_source_ids", "evidence_urls", "evidence_notes", "evidence_status", "ambiguity_warnings", "priority_score",
    "reviewer_decision", "reviewer_identifier", "review_date", "reviewer_justification", "final_review_status",
    "reviewed_canonical_class_id", "reviewed_canonical_name", "reviewed_category", "relationship_type",
    "evidence_support_type", "evidence_references", "decision_authentication_status", "integration_status",
]
DECISION_DIGEST_FIELDS = (
    "candidate_id", "reviewer_decision", "reviewer_identifier", "review_date", "reviewer_justification",
    "reviewed_canonical_class_id", "reviewed_canonical_name", "reviewed_category", "relationship_type",
    "evidence_support_type", "evidence_references",
)


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        return list(reader), fields


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decision_record_digest(row: dict) -> str:
    payload = {field: str(row.get(field, "") or "").strip() for field in DECISION_DIGEST_FIELDS}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _has_reference(value: str) -> bool:
    refs = [part.strip() for part in value.split(";") if part.strip()]
    return any(ref.lower().startswith(("https://", "http://", "doi:")) or re.search(r"\b(?:21\s*CFR|CFR|Codex|Regulation\s*\(?EU|GRN\s*\d+|E\s*\d{3,4})\b", ref, re.I) for ref in refs)


def load_trusted_attestors(path: Path | None) -> set[str]:
    if path is None:
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    values = data.get("trusted_attestors", []) if isinstance(data, dict) else data
    if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
        raise ValueError("trusted attestor file must be a JSON list or {'trusted_attestors': [...]} of non-empty IDs")
    return {x.strip() for x in values}


def _canonical_maps(taxonomy) -> tuple[dict[str, object], dict[str, set[str]]]:
    by_id = {item.class_id: item for item in taxonomy}
    owners: dict[str, set[str]] = defaultdict(set)
    for item in taxonomy:
        owners[normalize_candidate(item.canonical_name)].add(item.class_id)
        for alias in item.aliases:
            owners[normalize_candidate(alias)].add(item.class_id)
    return by_id, owners


def _auth_map(attestation_rows: list[dict], trusted_attestors: set[str]) -> tuple[dict[str, dict], list[dict]]:
    quarantine: list[dict] = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for index, row in enumerate(attestation_rows, 2):
        grouped[row.get("candidate_id", "")].append({**row, "_line": index})
    accepted = {}
    for candidate, rows in grouped.items():
        if len(rows) != 1:
            for row in rows:
                quarantine.append({"record_type": "attestation", "source_row": row["_line"], "candidate_id": candidate, "decision": "", "reason_code": "duplicate_attestation", "reason": "more than one attestation record for candidate"})
            continue
        row = rows[0]
        missing = [field for field in ATTESTATION_FIELDS if not str(row.get(field, "")).strip()]
        if missing:
            quarantine.append({"record_type": "attestation", "source_row": row["_line"], "candidate_id": candidate, "decision": "", "reason_code": "incomplete_attestation", "reason": "missing " + ", ".join(missing)})
            continue
        if row["attestor_identifier"] not in trusted_attestors:
            quarantine.append({"record_type": "attestation", "source_row": row["_line"], "candidate_id": candidate, "decision": "", "reason_code": "untrusted_attestor", "reason": "attestor is not in the separately configured trusted-attestor allowlist"})
            continue
        try:
            datetime.fromisoformat(row["attested_at"].replace("Z", "+00:00"))
        except ValueError:
            quarantine.append({"record_type": "attestation", "source_row": row["_line"], "candidate_id": candidate, "decision": "", "reason_code": "invalid_attestation_timestamp", "reason": "attested_at must be an ISO date/time"})
            continue
        accepted[candidate] = row
    return accepted, quarantine


def validate_decisions(
    candidate_rows: list[dict], evidence_rows: list[dict], decision_rows: list[dict],
    attestation_rows: list[dict] | None = None, trusted_attestors: set[str] | None = None,
    taxonomy=TAXONOMY,
) -> dict:
    """Validate reviewer claims; authenticate only by separately trusted attestation."""
    attestation_rows = attestation_rows or []
    trusted_attestors = trusted_attestors or set()
    known = {row["candidate_id"]: row for row in candidate_rows}
    if len(known) != len(candidate_rows):
        raise ValueError("candidate register contains duplicate candidate IDs")
    evidence = {row["candidate_id"]: row for row in evidence_rows}
    by_class, alias_owners = _canonical_maps(taxonomy)
    attested, quarantine = _auth_map(attestation_rows, trusted_attestors)
    for cid, row in list(attested.items()):
        if cid not in known:
            quarantine.append({"record_type": "attestation", "source_row": row.get("_line", ""), "candidate_id": cid, "decision": "", "reason_code": "unknown_attestation_candidate", "reason": "attestation candidate ID is not in the Phase 6B-2 shortlist"})
            del attested[cid]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for line, row in enumerate(decision_rows, 2):
        grouped[str(row.get("candidate_id", ""))].append({**row, "_line": line})
    validated: list[dict] = []
    for cid, records in grouped.items():
        if len(records) > 1:
            decisions = {str(r.get("reviewer_decision", "")) for r in records}
            reason = "conflicting duplicate decisions" if len(decisions) > 1 else "duplicate decision records"
            code = "conflicting_decisions" if len(decisions) > 1 else "duplicate_decisions"
            for row in records:
                quarantine.append({"record_type": "decision", "source_row": row["_line"], "candidate_id": cid, "decision": row.get("reviewer_decision", ""), "reason_code": code, "reason": reason})
            continue
        row = records[0]
        reasons: list[tuple[str, str]] = []
        decision = str(row.get("reviewer_decision", "")).strip()
        if not decision and not any(str(row.get(field, "")).strip() for field in DECISION_FIELDS if field not in {"candidate_id", "candidate_phrase", "reviewer_decision"}):
            # Unedited reviewer templates intentionally contain blank decisions.
            continue
        if cid not in known:
            reasons.append(("unknown_candidate_id", "candidate ID is not in the Phase 6B-2 shortlist"))
        if decision not in DECISIONS:
            reasons.append(("invalid_decision", f"unsupported decision value: {decision}"))
        if cid in known and row.get("candidate_phrase", "").strip() and normalize_candidate(row["candidate_phrase"]) != known[cid]["normalized_phrase"]:
            reasons.append(("candidate_phrase_mismatch", "candidate phrase does not match candidate ID"))
        reviewer = str(row.get("reviewer_identifier", "")).strip()
        if not reviewer:
            reasons.append(("missing_reviewer", "reviewer identifier is required for a recorded decision"))
        review_date = str(row.get("review_date", "")).strip()
        try:
            parsed_date = date.fromisoformat(review_date)
            if parsed_date > date.today():
                reasons.append(("future_review_date", "review date cannot be in the future"))
        except ValueError:
            reasons.append(("invalid_review_date", "review_date must use ISO YYYY-MM-DD"))
        if not str(row.get("reviewer_justification", "")).strip():
            reasons.append(("missing_justification", "reviewer justification is required for recorded decisions"))
        if decision in {"approve_existing_class_alias", "approve_new_ingredient_concept", "approve_additive_concept"}:
            support_type = str(row.get("evidence_support_type", "")).strip()
            refs = str(row.get("evidence_references", "")).strip()
            if support_type not in EVIDENCE_SUPPORT_TYPES - {"terminology_only"}:
                reasons.append(("insufficient_evidence_type", "approval requires evidence supporting the specific identity/relationship, not terminology-only evidence"))
            if not refs or not _has_reference(refs):
                reasons.append(("missing_evidence_reference", "approval requires a specific evidence URL or document identifier"))
            if decision == "approve_existing_class_alias":
                target_id = str(row.get("reviewed_canonical_class_id", "")).strip()
                target_name = str(row.get("reviewed_canonical_name", "")).strip()
                relationship = str(row.get("relationship_type", "")).strip()
                if target_id not in by_class:
                    reasons.append(("invalid_canonical_class_id", "approved alias must reference an existing canonical class ID"))
                elif target_name.casefold() != by_class[target_id].canonical_name.casefold():
                    reasons.append(("canonical_name_mismatch", "canonical name does not match the referenced class ID"))
                if relationship not in {"synonym", "common_name", "spelling_variant"}:
                    reasons.append(("invalid_alias_relationship", "existing-class alias approval requires a same-identity synonym/common-name/spelling-variant relationship"))
                if cid in known and target_id in by_class:
                    phrase = known[cid]["normalized_phrase"]
                    owners = alias_owners.get(phrase, set())
                    if phrase == normalize_candidate(by_class[target_id].canonical_name):
                        reasons.append(("not_an_alias", "candidate is already the target canonical name"))
                    if any(owner != target_id for owner in owners):
                        reasons.append(("alias_collision", "candidate phrase collides with another canonical class or declared alias"))
                if support_type not in {"synonym_identity", "ingredient_identity"}:
                    reasons.append(("alias_evidence_mismatch", "alias approval requires evidence of same ingredient identity"))
            else:
                name = str(row.get("reviewed_canonical_name", "")).strip()
                category = str(row.get("reviewed_category", "")).strip()
                relationship = str(row.get("relationship_type", "")).strip()
                if not name:
                    reasons.append(("missing_proposed_canonical_name", "new concept approval requires a proposed canonical name"))
                if category not in {"ingredient", "additive"}:
                    reasons.append(("invalid_new_concept_category", "new concept category must be ingredient or additive"))
                expected_category = "ingredient" if decision == "approve_new_ingredient_concept" else "additive"
                if category and category != expected_category:
                    reasons.append(("decision_category_mismatch", f"decision requires category {expected_category}"))
                if normalize_candidate(name) in alias_owners:
                    reasons.append(("new_concept_name_collision", "proposed name collides with an existing canonical class or alias"))
                expected_relationships = {"distinct_ingredient", "ingredient_derivative"} if decision == "approve_new_ingredient_concept" else {"distinct_additive"}
                if relationship not in expected_relationships:
                    reasons.append(("invalid_new_concept_relationship", "relationship type is inconsistent with the approval decision"))
                allowed_support = {"ingredient_identity", "distinct_concept"} if decision == "approve_new_ingredient_concept" else {"additive_identity", "regulatory_identity_or_use"}
                if support_type not in allowed_support:
                    reasons.append(("new_concept_evidence_mismatch", "evidence type does not support the proposed ingredient/additive concept"))
        if reasons:
            for code, detail in reasons:
                quarantine.append({"record_type": "decision", "source_row": row["_line"], "candidate_id": cid, "decision": decision, "reason_code": code, "reason": detail})
            continue
        digest = decision_record_digest(row)
        attestation = attested.get(cid)
        authenticated = bool(attestation and attestation.get("review_record_sha256", "").casefold() == digest.casefold() and attestation.get("attestor_identifier") != reviewer)
        auth_status = "independently_attested" if authenticated else "unattested_claim"
        if attestation and not authenticated:
            quarantine.append({"record_type": "attestation", "source_row": attestation.get("_line", ""), "candidate_id": cid, "decision": decision, "reason_code": "attestation_digest_or_independence_mismatch", "reason": "attestation digest did not match the reviewer record or attestor was not independent"})
        validated.append({**{k: str(row.get(k, "") or "").strip() for k in DECISION_FIELDS},
                          "review_source": row.get("_source", "").strip(), "review_record_sha256": digest,
                          "decision_authentication_status": auth_status, "attestor_identifier": attestation.get("attestor_identifier", "") if authenticated else "",
                          "attestation_reference": attestation.get("attestation_reference", "") if authenticated else "",
                          "review_status": "human_reviewed" if authenticated else "not_human_reviewed"})
    # Unknown-candidate decisions with duplicate rows are handled above; unattached attestations are not silently trusted.
    decision_candidate_ids = set(grouped)
    for cid, attestation in attested.items():
        if cid not in decision_candidate_ids:
            quarantine.append({"record_type": "attestation", "source_row": attestation.get("_line", ""), "candidate_id": cid, "decision": "", "reason_code": "orphan_attestation", "reason": "attestation has no matching imported decision record"})
    return {"validated": validated, "quarantined": quarantine, "trusted_attestation_count": sum(x["decision_authentication_status"] == "independently_attested" for x in validated)}


def _batch_rows(records: list[dict], target_size: int = 50) -> list[list[dict]]:
    if not records:
        return []
    count = max(1, int(len(records) / target_size + 0.5))
    base, extra = divmod(len(records), count)
    sizes = [base + (index < extra) for index in range(count)]
    batches = []
    offset = 0
    for size in sizes:
        batches.append(records[offset:offset + size])
        offset += size
    return batches


def _record_from_sources(short: dict, evidence: dict, batch_id: str) -> dict:
    proposed_identity = short.get("proposed_existing_class_name") or short.get("proposed_new_concept") or short.get("candidate_phrase", "")
    relationship_type = "existing_class_synonym_proposal" if short.get("proposed_existing_class_id") else "compound_expression_pending" if short.get("discovery_category") == "compound_ingredient_expression" else "new_concept_candidate" if short.get("proposed_new_concept") else "unresolved_candidate"
    return {
        "batch_id": batch_id, "candidate_id": short["candidate_id"], "candidate_phrase": short.get("candidate_phrase", ""),
        "normalized_phrase": short["normalized_phrase"], "discovery_category": short["discovery_category"],
        "discovery_status": short.get("discovery_status", "candidate"), "source_occurrence_count": short.get("source_occurrence_count", "0"),
        "original_source_references": evidence.get("original_source_references", "[]"), "proposed_ingredient_identity": proposed_identity,
        "proposed_relationship_type": relationship_type, "proposed_relationship": short.get("proposed_relationship", ""),
        "proposed_canonical_class_id": short.get("proposed_existing_class_id", ""),
        "proposed_canonical_class_name": short.get("proposed_existing_class_name", ""),
        "proposed_new_concept": short.get("proposed_new_concept", ""),
        "evidence_source_ids": evidence.get("evidence_source_id", ""), "evidence_urls": evidence.get("evidence_url", ""),
        "evidence_notes": evidence.get("evidence_summary", ""), "evidence_status": evidence.get("evidence_status", "not_checked"),
        "ambiguity_warnings": evidence.get("ambiguity_notes", ""), "priority_score": short.get("priority_score", ""),
        "reviewer_decision": "", "reviewer_identifier": "", "review_date": "", "reviewer_justification": "",
        "reviewed_canonical_class_id": "", "reviewed_canonical_name": "", "reviewed_category": "",
        "relationship_type": "", "evidence_support_type": "", "evidence_references": "",
        "final_review_status": "pending_human_review", "decision_authentication_status": "no_decision_imported", "integration_status": "not_integrated",
    }


def _reconcile_phase6b2(base: Path, shortlist: list[dict], deferred: list[dict], evidence_registry: list[dict]) -> dict:
    output = base / "phase6b2"
    report = json.loads((output / "prioritization_report.json").read_text(encoding="utf-8"))
    mapping_rows, _ = read_csv(output / "proposed_existing_class_mappings.csv")
    concept_rows, _ = read_csv(output / "proposed_new_ingredient_concepts.csv")
    additive_rows, _ = read_csv(output / "proposed_additive_candidates.csv")
    compound_rows, _ = read_csv(output / "compound_investigation_queue.csv")
    short_by_id = {row["candidate_id"]: row for row in shortlist}
    native_additives = [r for r in additive_rows if short_by_id.get(r["candidate_id"], {}).get("discovery_category") == "possible_additive"]
    cross_category = [r for r in additive_rows if r not in native_additives]
    extra_categories = Counter(short_by_id.get(r["candidate_id"], {}).get("discovery_category", "unknown") for r in cross_category)
    return {
        "shortlist_count": len(shortlist), "deferred_count": len(deferred), "shortlist_deferred_reconcile": len(shortlist) + len(deferred) == report.get("discovery_inventory_rows"),
        "shortlist_counts_by_discovery_category": dict(sorted(Counter(r["discovery_category"] for r in shortlist).items())),
        "proposed_existing_class_mapping_count": len(mapping_rows), "proposed_new_concept_count": len(concept_rows),
        "proposed_additive_candidate_count": len(additive_rows), "compound_investigation_record_count": len(compound_rows),
        "additive_proposal_reconciliation": {
            "possible_additive_category_candidates": len(native_additives), "additional_evidence_based_cross_category_candidates": len(cross_category),
            "cross_category_counts": dict(sorted(extra_categories.items())), "total_proposed_additives": len(additive_rows),
            "unique_candidate_ids": len({r["candidate_id"] for r in additive_rows}),
            "additional_candidate_phrases": [short_by_id[r["candidate_id"]]["normalized_phrase"] for r in cross_category],
            "explanation": "The additive proposal export includes all 150 possible_additive discovery rows plus evidence-based additive proposals from other discovery categories; this is overlap in proposed use, not a discovery-category recount.",
        },
        "evidence_status_counts": dict(sorted(Counter(r.get("evidence_status", "not_checked") for r in evidence_registry).items())),
    }


def build_review_workflow(
    phase6b2_dir: Path, output_dir: Path, decision_path: Path | None = None,
    attestation_path: Path | None = None, trusted_attestors: set[str] | None = None,
    taxonomy=TAXONOMY, integrity_paths: dict[str, Path] | None = None,
) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing review workflow output: {output_dir}")
    trusted_attestors = trusted_attestors or set()
    shortlist, _ = read_csv(phase6b2_dir / "priority_shortlist.csv")
    evidence_rows, _ = read_csv(phase6b2_dir / "candidate_evidence_registry.csv")
    deferred, _ = read_csv(phase6b2_dir / "deferred_candidates.csv")
    if len({row["candidate_id"] for row in shortlist}) != len(shortlist):
        raise ValueError("Phase 6B-2 shortlist has duplicate candidate IDs")
    evidence_by_id = {row["candidate_id"]: row for row in evidence_rows}
    if set(evidence_by_id) != {row["candidate_id"] for row in shortlist}:
        raise ValueError("candidate evidence registry does not cover the shortlist exactly")
    candidates = sorted(shortlist, key=lambda row: (-int(row.get("priority_score") or 0), -int(row.get("source_occurrence_count") or 0), row["candidate_id"]))
    chunks = _batch_rows(candidates)
    batches: list[dict] = []
    batch_id_by_candidate = {}
    for index, chunk in enumerate(chunks, 1):
        bid = f"BATCH-{index:03d}"
        filename = f"review_batch_{index:03d}.csv"
        records = [_record_from_sources(row, evidence_by_id[row["candidate_id"]], bid) for row in chunk]
        for row in records:
            batch_id_by_candidate[row["candidate_id"]] = bid
        batches.append({"batch_id": bid, "filename": filename, "candidate_count": len(records), "candidate_ids": "|".join(row["candidate_id"] for row in records), "records": records})

    decision_rows = []
    decision_sha = ""
    if decision_path:
        decision_rows, fields = read_csv(decision_path)
        if not set(DECISION_FIELDS).issubset(fields):
            raise ValueError(f"decision import missing required fields: {sorted(set(DECISION_FIELDS) - set(fields))}")
        decision_sha = sha256_file(decision_path)
        for row in decision_rows:
            row["_source"] = str(decision_path.as_posix())
    attestation_rows = []
    attestation_sha = ""
    if attestation_path:
        attestation_rows, fields = read_csv(attestation_path)
        if not set(ATTESTATION_FIELDS).issubset(fields):
            raise ValueError(f"attestation import missing required fields: {sorted(set(ATTESTATION_FIELDS) - set(fields))}")
        attestation_sha = sha256_file(attestation_path)
    validation = validate_decisions(shortlist, evidence_rows, decision_rows, attestation_rows, trusted_attestors, taxonomy)
    validated = validation["validated"]
    quarantine = validation["quarantined"]
    claims_by_candidate = {row["candidate_id"]: row for row in validated}
    # Build register, authenticated decisions only change review status.
    register = []
    approved, rejected, unresolved = [], [], []
    for candidate in candidates:
        cid = candidate["candidate_id"]
        record = _record_from_sources(candidate, evidence_by_id[cid], batch_id_by_candidate[cid])
        claim = claims_by_candidate.get(cid)
        if claim:
            record.update({
                "reviewer_decision": claim["reviewer_decision"], "reviewer_identifier": claim["reviewer_identifier"],
                "review_date": claim["review_date"], "reviewer_justification": claim["reviewer_justification"],
                "final_review_status": "human_reviewed" if claim["decision_authentication_status"] == "independently_attested" else "unresolved_unattested_claim",
                "decision_authentication_status": claim["decision_authentication_status"],
            })
            if claim["decision_authentication_status"] == "independently_attested" and claim["reviewer_decision"].startswith("approve_"):
                approved.append({**record, **claim, "final_review_status": "human_reviewed", "integration_status": "not_integrated"})
            elif claim["decision_authentication_status"] == "independently_attested" and claim["reviewer_decision"] == "reject":
                rejected.append({**record, **claim, "final_review_status": "human_reviewed", "integration_status": "not_integrated"})
            else:
                unresolved.append({**record, "unresolved_reason": "decision claim lacks accepted independent attestation" if claim["decision_authentication_status"] != "independently_attested" else f"decision is {claim['reviewer_decision']}"})
        else:
            unresolved.append({**record, "unresolved_reason": "awaiting human review"})
        register.append(record)

    output_dir.mkdir(parents=True)
    batch_dir = output_dir / "review_batches"
    batch_dir.mkdir()
    manifest = []
    for batch in batches:
        write_csv(batch_dir / batch["filename"], batch["records"], REGISTER_FIELDS)
        manifest.append({k: batch[k] for k in ("batch_id", "filename", "candidate_count", "candidate_ids")})
    write_csv(output_dir / "review_manifest.csv", manifest, ["batch_id", "filename", "candidate_count", "candidate_ids"])
    write_csv(output_dir / "candidate_review_register.csv", register, REGISTER_FIELDS)
    validated_fields = DECISION_FIELDS + ["review_source", "review_record_sha256", "decision_authentication_status", "attestor_identifier", "attestation_reference", "review_status"]
    write_csv(output_dir / "validated_review_decisions.csv", validated, validated_fields)
    export_fields = REGISTER_FIELDS + ["review_record_sha256", "attestor_identifier", "attestation_reference"]
    write_csv(output_dir / "approved_candidates.csv", approved, export_fields)
    write_csv(output_dir / "rejected_candidates.csv", rejected, export_fields)
    write_csv(output_dir / "unresolved_candidates.csv", unresolved, REGISTER_FIELDS + ["unresolved_reason"])
    write_csv(output_dir / "quarantined_review_records.csv", quarantine, ["record_type", "source_row", "candidate_id", "decision", "reason_code", "reason"])

    reconciliation = _reconcile_phase6b2(phase6b2_dir.parent, shortlist, deferred, evidence_rows)
    integrity = {}
    for label, path in (integrity_paths or {}).items():
        if path.exists():
            integrity[label] = {"path": path.as_posix(), "sha256": sha256_file(path)}
    authenticated_decisions = len([row for row in validated if row["decision_authentication_status"] == "independently_attested"])
    genuine_approval_count = sum(row["decision_authentication_status"] == "independently_attested" and row["reviewer_decision"].startswith("approve_") for row in validated)
    decisions_by_value = dict(sorted(Counter(row["reviewer_decision"] for row in validated).items()))
    report = {
        "pipeline_version": "FoodLence V4 Phase 6B-3", "phase6b2_reconciliation": reconciliation,
        "review_batch_count": len(batches), "review_candidate_count": len(register),
        "review_batch_sizes": [batch["candidate_count"] for batch in batches],
        "each_shortlisted_candidate_in_exactly_one_batch": sum(batch["candidate_count"] for batch in batches) == len(shortlist) and len(batch_id_by_candidate) == len(shortlist),
        "reviewer_decisions_imported": len(decision_rows), "syntactically_valid_decision_claims": len(validated),
        "genuinely_attested_review_decisions": authenticated_decisions,
        "unattested_decision_claims": sum(row["decision_authentication_status"] == "unattested_claim" for row in validated),
        "decision_counts_by_value": decisions_by_value, "approved_count": len(approved), "rejected_count": len(rejected),
        "unresolved_count": len(unresolved), "quarantined_record_count": len(quarantine),
        "reviewer_fields_blank_in_unreviewed_templates": all(not row["reviewer_decision"] and not row["reviewer_identifier"] and not row["review_date"] and not row["reviewer_justification"] for row in register if not row["reviewer_decision"]),
        "genuinely_attested_approval_count": genuine_approval_count,
        "approved_export_empty_without_genuine_attestation": genuine_approval_count > 0 or len(approved) == 0,
        "taxonomy_modified": False, "authoritative_ingredient_data_modified": False, "splits_modified": False,
        "phase5_allergen_data_modified": False, "training_pipeline_connected": False,
        "decision_import_sha256": decision_sha, "attestation_import_sha256": attestation_sha,
        "trusted_attestor_allowlist_count": len(trusted_attestors), "integrity_input_hashes": integrity,
        "authentication_policy": "CSV reviewer identity/decision fields alone are unauthenticated claims. Only an external attestation with a matching decision digest, a different attestor, a non-empty reference, and an attestor ID in a separately supplied trusted allowlist can mark a decision human_reviewed. No trust allowlist or genuine review decisions were supplied for this run.",
        "limitations": ["No human review decisions or attestation records were provided; every candidate remains pending and the approved/rejected exports are empty.", "External attestation references are not independently fetched or cryptographically verified by this local workflow; trust depends on the provenance of the allowlist and attestation process.", "A structurally valid evidence URL/reference and reviewer assessment remain claims until authenticated review; the code does not decide scientific identity."],
    }
    (output_dir / "review_reconciliation_report.json").write_text(json.dumps(reconciliation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "review_audit_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "review_workflow_guide.md").write_text(_guide(report), encoding="utf-8")
    return report


def _guide(report: dict) -> str:
    return """# FoodLence V4 candidate review workflow

## How to review

Open a CSV in `review_batches/` and complete reviewer fields for only the records you actually reviewed. Leave decisions blank when undecided. Do not edit candidate IDs. A decision CSV must preserve the review columns shown in the batch and include `reviewed_canonical_class_id`, `reviewed_canonical_name`, `reviewed_category`, `relationship_type`, `evidence_support_type`, and `evidence_references` when applicable.

Allowed decisions are `approve_existing_class_alias`, `approve_new_ingredient_concept`, `approve_additive_concept`, `requires_more_evidence`, `reject`, and `defer`. Approvals require a reviewer ID, ISO review date, justification, an exact evidence reference, and an evidence-support type that supports the specific identity/relationship. Existing-class aliases must name a valid existing class and use a same-identity synonym/common-name/spelling-variant relationship. New concepts must be distinct from current canonical names and aliases.

## Authenticity and import

Reviewer-supplied CSV fields are claims, not proof of identity or authorization. To mark a decision `human_reviewed`, import an independent attestation CSV with `candidate_id`, `review_record_sha256`, `attestor_identifier`, `attested_at`, and `attestation_reference`, and provide a separately maintained trusted-attestor JSON allowlist. The attestor must differ from the reviewer. The digest is computed with `decision_record_digest()` from the canonical decision fields. Do not place reviewer IDs into the trusted list without project authorization. This tool does not verify external attestation URLs or signatures.

Run `python ml/data/review_foodlence_vocabulary.py --help`. A new output directory is required for each immutable review run; existing Phase 6B-3 outputs are never overwritten. With no authentic imported decisions, all candidates remain pending/unresolved and `approved_candidates.csv` stays empty. Even attested approvals remain `not_integrated`; this workflow is disconnected from taxonomy and training builders.

## This run

- Candidates prepared: """ + str(report["review_candidate_count"]) + "\n- Review batches: " + str(report["review_batch_count"]) + "\n- Genuine reviewer decisions: " + str(report["genuinely_attested_review_decisions"]) + "\n- Approved export rows: " + str(report["approved_count"]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).parents[1] / "foodlence_generated_v4"
    parser.add_argument("--phase6b2-dir", type=Path, default=root / "phase6b2")
    parser.add_argument("--output-dir", type=Path, default=root / "phase6b3")
    parser.add_argument("--import-decisions", type=Path, help="reviewer decision CSV; imported values remain claims until attested")
    parser.add_argument("--attestations", type=Path, help="separate independent attestation CSV")
    parser.add_argument("--trusted-attestors-file", type=Path, help="externally maintained JSON allowlist of trusted attestor IDs")
    parser.add_argument("--prepare-batches", action="store_true", help="prepare reviewer batches (default when no decision import is provided)")
    args = parser.parse_args()
    trusted = load_trusted_attestors(args.trusted_attestors_file)
    data_root = Path(__file__).parents[1]
    hashes = {
        "taxonomy": data_root / "v4" / "taxonomy.py",
        "authoritative_ingredients_all": root / "phase4b_corrected" / "ingredients_all.csv",
        "ingredients_train": root / "phase4b_corrected" / "ingredients_train.csv",
        "ingredients_validation": root / "phase4b_corrected" / "ingredients_validation.csv",
        "ingredients_test": root / "phase4b_corrected" / "ingredients_test.csv",
    }
    report = build_review_workflow(args.phase6b2_dir, args.output_dir, args.import_decisions, args.attestations, trusted, integrity_paths=hashes)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

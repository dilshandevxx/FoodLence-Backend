import csv
import json
from pathlib import Path

from ml.data.v4.review_vocabulary import (
    ATTESTATION_FIELDS,
    DECISION_FIELDS,
    build_review_workflow,
    decision_record_digest,
    read_csv,
    validate_decisions,
)


ROOT = Path(__file__).parents[1]
PHASE6B2 = ROOT / "ml/data/foodlence_generated_v4/phase6b2"


def _decision(candidate, **kwargs):
    row = {field: "" for field in DECISION_FIELDS}
    row.update(candidate_id=candidate["candidate_id"], candidate_phrase=candidate["candidate_phrase"], **kwargs)
    return row


def _candidate_and_evidence():
    candidates, _ = read_csv(PHASE6B2 / "priority_shortlist.csv")
    evidence, _ = read_csv(PHASE6B2 / "candidate_evidence_registry.csv")
    return candidates, evidence


def test_phase6b2_register_and_provenance_coverage():
    candidates, evidence = _candidate_and_evidence()
    assert len(candidates) == 452
    assert {x["candidate_id"] for x in evidence} == {x["candidate_id"] for x in candidates}
    assert all(json.loads(x["original_source_references"]) for x in evidence)


def test_blank_template_and_no_decisions_stay_pending():
    candidates, evidence = _candidate_and_evidence()
    result = validate_decisions(candidates, evidence, [])
    assert result["validated"] == []
    assert result["quarantined"] == []


def test_invalid_class_reference_and_missing_reviewer_are_quarantined():
    candidates, evidence = _candidate_and_evidence()
    candidate = candidates[0]
    decision = _decision(candidate, reviewer_decision="approve_existing_class_alias", reviewed_canonical_class_id="FL-999", reviewed_canonical_name="Unknown", relationship_type="synonym", evidence_support_type="synonym_identity", evidence_references="https://example.org/evidence", reviewer_date="2026-01-01")
    # Required spelling is review_date; the malformed row must not be accepted.
    result = validate_decisions(candidates, evidence, [decision])
    codes = {row["reason_code"] for row in result["quarantined"]}
    assert "invalid_canonical_class_id" in codes
    assert "missing_reviewer" in codes
    assert "invalid_review_date" in codes


def test_unattested_claim_never_counts_as_human_reviewed():
    candidates, evidence = _candidate_and_evidence()
    candidate = next(row for row in candidates if row["proposed_existing_class_id"])
    decision = _decision(candidate, reviewer_decision="approve_existing_class_alias", reviewer_identifier="reviewer-a", review_date="2026-01-15", reviewer_justification="Reviewed source identity.", reviewed_canonical_class_id=candidate["proposed_existing_class_id"], reviewed_canonical_name=candidate["proposed_existing_class_name"], relationship_type="synonym", evidence_support_type="synonym_identity", evidence_references="https://example.org/evidence")
    result = validate_decisions(candidates, evidence, [decision])
    assert result["validated"][0]["review_status"] == "not_human_reviewed"
    assert result["validated"][0]["decision_authentication_status"] == "unattested_claim"


def test_matching_attestation_requires_separate_trusted_independent_attestor():
    candidates, evidence = _candidate_and_evidence()
    candidate = next(row for row in candidates if row["proposed_existing_class_id"])
    decision = _decision(candidate, reviewer_decision="approve_existing_class_alias", reviewer_identifier="reviewer-a", review_date="2026-01-15", reviewer_justification="Reviewed source identity.", reviewed_canonical_class_id=candidate["proposed_existing_class_id"], reviewed_canonical_name=candidate["proposed_existing_class_name"], relationship_type="synonym", evidence_support_type="synonym_identity", evidence_references="https://example.org/evidence")
    attestation = {field: "" for field in ATTESTATION_FIELDS}
    attestation.update(candidate_id=candidate["candidate_id"], review_record_sha256=decision_record_digest(decision), attestor_identifier="independent-a", attested_at="2026-01-16T12:00:00Z", attestation_reference="review-log/1")
    result = validate_decisions(candidates, evidence, [decision], [attestation], {"independent-a"})
    assert result["validated"][0]["review_status"] == "human_reviewed"
    assert result["trusted_attestation_count"] == 1
    bad = dict(attestation, review_record_sha256="0" * 64)
    result = validate_decisions(candidates, evidence, [decision], [bad], {"independent-a"})
    assert result["validated"][0]["review_status"] == "not_human_reviewed"


def test_review_package_is_deterministic_and_empty_approval_export(tmp_path):
    reports = []
    for suffix in ("one", "two"):
        output = tmp_path / suffix
        reports.append(build_review_workflow(PHASE6B2, output))
        approved, _ = read_csv(output / "approved_candidates.csv")
        register, _ = read_csv(output / "candidate_review_register.csv")
        assert not approved
        assert len(register) == 452
        assert all(row["review_status"] if "review_status" in row else row["final_review_status"] == "pending_human_review" for row in register)
        assert (output / "review_batches").is_dir()
    assert reports[0]["review_batch_sizes"] == reports[1]["review_batch_sizes"]
    assert reports[0]["phase6b2_reconciliation"] == reports[1]["phase6b2_reconciliation"]
    assert reports[0]["approved_export_empty_without_genuine_attestation"] is True

import csv
import json
from pathlib import Path

from ml.data.v4.review_pilot import build_review_pilot
from ml.data.v4.review_vocabulary import build_review_workflow, read_csv
from ml.data.v4.review_pilot import DECISION_FIELDS


ROOT = Path(__file__).parents[1]
DATA = ROOT / "ml/data/foodlence_generated_v4"


def _make(tmp_path, name="pilot"):
    return build_review_pilot(DATA / "phase6b2", DATA / "phase6b3", tmp_path / name, DATA / "phase4b_corrected/ingredients_all.csv")


def test_deterministic_first_fifty_and_stable_ids(tmp_path):
    report = _make(tmp_path)
    candidates, _ = read_csv(tmp_path / "pilot/pilot_candidates.csv")
    manifest, _ = read_csv(DATA / "phase6b3/review_manifest.csv")
    expected = manifest[0]["candidate_ids"].split("|")[:50]
    assert len(candidates) == 50
    assert [r["candidate_id"] for r in candidates] == expected
    assert report["all_candidates_from_phase6b2_shortlist"] is True
    assert report["candidate_ids_and_priority_scores_preserved"] is True


def test_evidence_sources_are_traceable_and_limited(tmp_path):
    _make(tmp_path)
    records, _ = read_csv(tmp_path / "pilot/pilot_evidence_registry.csv")
    by_phrase = {r["candidate_phrase"].casefold(): r for r in records}
    assert "hfpappexternal.fda.gov" in by_phrase["baking soda"]["source_url"]
    assert by_phrase["baking soda"]["evidence_type"] == "identity_and_synonym"
    assert by_phrase["mono - diglycerides"]["evidence_status"] == "insufficient_evidence"
    assert "does not establish" in by_phrase["glucose - fructose syrup"]["evidence_limitations"]
    assert "specific chemically modified corn starch" in by_phrase["corn starch - modified"]["evidence_limitations"]
    assert all(r["human_review_status"] == "not_human_reviewed" for r in records)


def test_missing_evidence_is_explicit_not_fabricated(tmp_path):
    _make(tmp_path)
    records, _ = read_csv(tmp_path / "pilot/pilot_evidence_registry.csv")
    missing = [r for r in records if r["evidence_status"] == "not_checked"]
    assert missing
    assert all(not r["source_url"] and r["evidence_type"] == "not_checked" for r in missing)


def test_conflict_screen_is_proposal_only_and_no_alias_activated(tmp_path):
    report = _make(tmp_path)
    conflicts, _ = read_csv(tmp_path / "pilot/pilot_taxonomy_conflicts.csv")
    assert len(conflicts) == 50
    assert all(r["status"] == "proposal_only_not_activated" for r in conflicts)
    assert report["proposal_only_no_taxonomy_changes"] is True


def test_reviewer_fields_blank_and_import_compatible(tmp_path):
    _make(tmp_path)
    sheet_path = tmp_path / "pilot/pilot_review_sheet.csv"
    sheet, fields = read_csv(sheet_path)
    assert set(DECISION_FIELDS).issubset(fields)
    assert all(not r[field] for r in sheet for field in DECISION_FIELDS if field not in {"candidate_id", "candidate_phrase"})
    report = build_review_workflow(DATA / "phase6b2", tmp_path / "import-run", decision_path=sheet_path)
    assert report["reviewer_decisions_imported"] == 50
    assert report["syntactically_valid_decision_claims"] == 0
    assert report["approved_count"] == 0


def test_example_review_template_separate_source_examples_only(tmp_path):
    _make(tmp_path)
    examples, _ = read_csv(tmp_path / "pilot/ingredient_example_review_template.csv")
    assert len(examples) == 50
    assert all(r["example_id"] and r["source_provenance"] for r in examples)
    assert all(r["existing_review_status"] != "human_reviewed" for r in examples)
    assert all(not r[k] for r in examples for k in ("reviewer_confirmed_class", "reviewer_decision", "reviewer_identity", "review_date", "justification", "review_attestation_reference"))


def test_outputs_reports_are_reproducible_and_no_approval(tmp_path):
    first = _make(tmp_path, "first")
    second = _make(tmp_path, "second")
    assert first == second
    for name in ("pilot_candidates.csv", "pilot_evidence_registry.csv", "pilot_taxonomy_conflicts.csv", "pilot_review_sheet.csv", "ingredient_example_review_template.csv", "pilot_evidence_report.json", "pilot_evidence_report.md", "pilot_reviewer_guide.md"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()
    assert first["no_approval_or_integration_performed"] is True

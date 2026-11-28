"""Build a deterministic evidence-enriched, non-approving vocabulary pilot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

from .review_vocabulary import DECISION_FIELDS, read_csv, sha256_file, write_csv
from .taxonomy import TAXONOMY

CHECKED = "2026-11-23"
FDA = "U.S. Food and Drug Administration"
SOURCES = {
    "baking soda": ("FDA-FS-SODIUMBICARBONATE", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=SODIUMBICARBONATE&set=FoodSubstances", FDA, "identity_and_synonym", "SODIUM BICARBONATE lists BAKING SODA (SODIUM BICARBONATE) among other names and gives CAS 144-55-8.", "The source phrase may refer to a mixture or product description; FDA terminology does not establish the context of each source occurrence.", "evidence_found", "Baking soda is listed as another name for sodium bicarbonate; this is evidence for a proposed synonym relationship, not taxonomy approval."),
    "food starch modified": ("FDA-FS-STARCHFOODMODIFIED", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=STARCHFOODMODIFIED&set=FoodSubstances", FDA, "exact_terminology", "FDA entry STARCH, FOOD, MODIFIED lists FOOD STARCH, MODIFIED as another name and cites 21 CFR 172.892.", "A broad modified-starch term is not interchangeable with modified corn starch or another source-specific starch.", "evidence_found", "Punctuation-normalized phrase is close to the listed term. Supports terminology review only, not source-specific identity or a class assignment."),
    "agar agar": ("FDA-FS-AGAR", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=AGAR&set=FoodSubstances", FDA, "identity_and_synonym", "FDA entry AGAR (GELIDIUM SPP.) lists AGAR-AGAR among other names and gives CAS 9002-18-0.", "FDA's named substance specifies Gelidium spp.; the source phrase does not establish species or source.", "evidence_found", "The listed other name supports agar-agar terminology for the named agar substance, not an activated taxonomy label for the source occurrence."),
    "mono diglycerides": ("FDA-FS-MONOANDDIGLYCERIDES", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=MONOANDDIGLYCERIDES&set=FoodSubstances", FDA, "related_terminology_only", "FDA entry is MONO- AND DIGLYCERIDES and lists mixed mono- and diglyceride names.", "Candidate phrase is 'mono - diglycerides'; the source does not establish whether 'and' was omitted by OCR or whether the phrase denotes the listed mixture.", "insufficient_evidence", "Related official terminology exists, but the candidate wording does not establish equivalence. Do not add an alias."),
    "glucose fructose syrup": ("CFR-21-184.1865", "https://www.govinfo.gov/content/pkg/CFR-2024-title21-vol3/xhtml/CFR-2024-title21-vol3-part184.html", "U.S. Government Publishing Office; FDA regulation", "related_terminology_only", "21 CFR 184.1865 describes corn syrup, commonly called glucose syrup, and says it may contain glucose, maltose, and higher saccharides.", "This is not a definition of glucose-fructose syrup and does not establish that the phrases are equivalent.", "insufficient_evidence", "Related corn-syrup terminology only; glucose-fructose syrup remains unclassified."),
    "corn starch modified": ("FDA-SRS-UNII-461P5CJN6T", "https://precision.fda.gov/uniisearch/srs/unii/461P5CJN6T", "FDA Substance Registration System", "narrow_identity_context", "FDA SRS record names MODIFIED CORN STARCH (1-OCTENYL SUCCINIC ANHYDRIDE), UNII 461P5CJN6T.", "The record is for a specific chemically modified corn starch; it does not establish identity with generic modified corn starch in the source.", "insufficient_evidence", "A chemically specific record was found. Do not generalize this identity to the candidate's unspecified modified corn starch."),
    "cocoa processed with alkali": ("CFR-21-163.112", "https://www.govinfo.gov/content/pkg/CFR-2013-title21-vol2/pdf/CFR-2013-title21-vol2-sec163-112.pdf", "U.S. Government Publishing Office; FDA regulation", "regulatory_nomenclature", "21 CFR 163.112 uses 'Processed with alkali' nomenclature for specified cocoa/chocolate products when alkali ingredients are used.", "The phrase describes processing/nomenclature, not a standalone additive or an identity equivalence to a canonical cocoa class.", "evidence_found", "Regulatory naming context supports the phrase as a cocoa processing descriptor; classification remains a reviewer decision."),
    "soy lecithin an emulsifier": ("FDA-GRN-186", "https://hfpappexternal.fda.gov/scripts/Fdcc/index.cfm?id=186&set=GRASNotices", FDA, "limited_terminology", "FDA GRAS Notice 186 is titled 'Soy lecithin enzymatically modified to have increased phosphatidylserine' and describes an ingredient use.", "This is a specific enzymatically modified soy lecithin preparation, not evidence that generic soy lecithin and lecithin are interchangeable in every context.", "insufficient_evidence", "A specific soy-lecithin preparation appears in an FDA notice; candidate includes a functional descriptor. No class mapping is proposed."),
    "citric acid": ("FDA-FS-CITRICACID", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=CITRICACID&order=ASC&search=citric+acid&set=FoodSubstances&sort=Sortterm_ID&startrow=1&type=basic", FDA, "identity_and_terminology", "FDA inventory names CITRIC ACID, gives CAS 77-92-9, lists other names, and cites multiple regulations including 21 CFR 184.1033.", "The regulatory inventory is not a blanket statement of authorization for every use; use-specific regulations still govern.", "evidence_found", "Candidate phrase includes 'acidity regulator' context; the underlying term citric acid is identified, but the function phrase is not part of the substance name."),
    "sodium alginate": ("FDA-FS-ALGINATESODIUM", "https://hfpappexternal.fda.gov/scripts/Fdcc/index.cfm?id=ALGINATESODIUM&set=FoodSubstances", FDA, "identity_and_synonym", "FDA entry ALGINATE, SODIUM lists SODIUM ALGINATE as another name and gives CAS 9005-38-3.", "This supports identity terminology only; it does not activate an alias or determine the source occurrence's context.", "evidence_found", "Candidate's substance term is explicitly listed by FDA as another name for sodium alginate."),
    "maltodextrin": ("FDA-FS-MALTODEXTRIN", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=MALTODEXTRIN&set=FoodSubstances", FDA, "terminology_variant", "FDA inventory lists MALTODEXTRIN, CAS 9050-36-6, and cites 21 CFR 184.1444.", "Candidate is written 'malto dextrin'; a spacing variation is plausible but not an approved alias or an automated correction.", "evidence_found", "Official matching term supports a reviewer investigation of the spacing variant. No alias is activated."),
    "silicon dioxide anti caking": ("FDA-FS-SILICONDIOXIDE", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=SILICONDIOXIDE&set=FoodSubstances", FDA, "identity_and_function_context", "FDA inventory lists SILICON DIOXIDE, CAS 7631-86-9, with silica as another name and anticaking among technical effects.", "Parenthetical anti-caking text is a functional descriptor; source does not prove it belongs in canonical substance text.", "evidence_found", "Substance and function are both represented in FDA inventory; keep descriptor separate from identity during review."),
    "tri calcium phosphate": ("FDA-FS-CALCIUMPHOSPHATETRIBASIC", "https://hfpappexternal.fda.gov/scripts/fdcc/index.cfm?id=CALCIUMPHOSPHATETRIBASIC&set=FoodSubstances", FDA, "identity_and_synonym", "FDA entry CALCIUM PHOSPHATE, TRIBASIC lists TRICALCIUM PHOSPHATE and gives CAS 7758-87-4.", "The normalized spacing variant is not an activated alias; compare the precise class definition and avoid mapping to a broader calcium-phosphate class without review.", "evidence_found", "FDA-listed name supports a same-substance terminology proposal, subject to a canonical taxonomy specificity check."),
}

EVIDENCE_FIELDS = ["candidate_id", "candidate_phrase", "proposed_ingredient_identity", "proposed_existing_class_id", "proposed_existing_class_name", "evidence_source_id", "source_organization", "source_url", "evidence_type", "evidence_summary", "matching_terminology", "evidence_limitations", "date_checked", "evidence_status", "human_review_status"]
CONFLICT_FIELDS = ["candidate_id", "candidate_phrase", "proposed_class_id", "proposed_class_name", "conflict_type", "finding", "ambiguity_flags", "evidence_source_id", "status"]
PILOT_FIELDS = DECISION_FIELDS + ["normalized_phrase", "discovery_category", "proposed_ingredient_identity", "proposed_class_id", "proposed_class_name", "priority_score", "source_occurrence_count", "original_source_references", "evidence_source_id", "source_organization", "source_url", "evidence_type", "evidence_summary", "matching_terminology", "evidence_limitations", "date_checked", "evidence_status", "potential_ambiguity", "human_review_status"]
EXAMPLE_FIELDS = ["example_id", "original_ingredient_label_text", "normalized_text", "proposed_canonical_class_id", "proposed_canonical_class", "source_provenance", "source_dataset", "source_row_id", "source_file_hash", "label_method", "validation_status", "existing_review_status", "reviewer_confirmed_class", "reviewer_decision", "reviewer_identity", "review_date", "justification", "review_attestation_reference"]


def _screen_flags(phrase: str) -> str:
    p = phrase.casefold()
    flags = []
    if " - " in p or "- " in p or " -" in p:
        flags.append("punctuation_or_tokenization_variant")
    if any(term in p for term in ("emulsifier", "regulator", "enriching substance", "anti caking")):
        flags.append("function_or_context_mixed_with_substance")
    if any(term in p for term in ("organic", "reduced", "free", "non hydrogenated", "non- hydrogenated", "farm raised", "expeller pressed", "gluten free", "pasteurized", "part skim")):
        flags.append("qualifier_or_processing_descriptor")
    if p in {"mono an", "beta ca", "non hydrogenated", "soy lecithin an", "soy lecithin a"} or p.endswith(" emuls") or p.endswith(" emulsif"):
        flags.append("possible_truncated_or_incomplete_phrase")
    return ";".join(flags) or "not_determined"


def _source_record(candidate: dict, original: dict) -> dict:
    phrase = candidate["candidate_phrase"]
    key = candidate["normalized_phrase"].casefold()
    record = original.get(candidate["candidate_id"], {})
    values = SOURCES.get(key)
    if values is None and key.endswith("citric acid"):
        values = SOURCES["citric acid"]
    if values is None and key == "malto dextrin":
        values = SOURCES["maltodextrin"]
    if values is None and key.startswith("silicon dioxide"):
        values = SOURCES["silicon dioxide anti caking"]
    if values:
        sid, url, org, etype, summary, limits, status, matching = values
        return {"candidate_id": candidate["candidate_id"], "candidate_phrase": phrase,
                "proposed_ingredient_identity": candidate.get("proposed_ingredient_identity", ""),
                "proposed_existing_class_id": candidate.get("proposed_canonical_class_id", ""),
                "proposed_existing_class_name": candidate.get("proposed_canonical_class_name", ""),
                "evidence_source_id": sid, "source_organization": org, "source_url": url,
                "evidence_type": etype, "evidence_summary": summary, "matching_terminology": matching,
                "evidence_limitations": limits, "date_checked": CHECKED, "evidence_status": status,
                "human_review_status": "not_human_reviewed"}
    # Preserve Phase 6B-2 evidence when it exists, but don't imply new verification.
    if record.get("evidence_source_ids") or record.get("evidence_urls"):
        eid = record.get("evidence_source_ids", "")
        url = record.get("evidence_urls", "")
        return {"candidate_id": candidate["candidate_id"], "candidate_phrase": phrase,
                "proposed_ingredient_identity": candidate.get("proposed_ingredient_identity", ""),
                "proposed_existing_class_id": candidate.get("proposed_canonical_class_id", ""),
                "proposed_existing_class_name": candidate.get("proposed_canonical_class_name", ""),
                "evidence_source_id": eid, "source_organization": "Phase 6B-2 evidence registry; source organization not independently established in this pilot",
                "source_url": url, "evidence_type": "prior_unverified_evidence_record",
                "evidence_summary": record.get("evidence_notes", ""), "matching_terminology": "",
                "evidence_limitations": record.get("ambiguity_warnings", "") or "Source claim preserved; pilot did not independently validate this reference.",
                "date_checked": "", "evidence_status": "not_checked", "human_review_status": "not_human_reviewed"}
    return {"candidate_id": candidate["candidate_id"], "candidate_phrase": phrase,
            "proposed_ingredient_identity": candidate.get("proposed_ingredient_identity", ""),
            "proposed_existing_class_id": candidate.get("proposed_canonical_class_id", ""),
            "proposed_existing_class_name": candidate.get("proposed_canonical_class_name", ""),
            "evidence_source_id": "", "source_organization": "", "source_url": "", "evidence_type": "not_checked",
            "evidence_summary": "No candidate-specific authoritative evidence was recorded in this pilot pass.",
            "matching_terminology": "", "evidence_limitations": "No conclusion about identity, synonymy, or regulatory status can be drawn.",
            "date_checked": "", "evidence_status": "not_checked", "human_review_status": "not_human_reviewed"}


def build_review_pilot(phase6b2_dir: Path, phase6b3_dir: Path, output_dir: Path, examples_path: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing pilot output: {output_dir}")
    manifest, _ = read_csv(phase6b3_dir / "review_manifest.csv")
    if not manifest:
        raise ValueError("Phase 6B-3 review manifest is empty")
    batch1 = phase6b3_dir / "review_batches" / manifest[0]["filename"]
    first_batch, _ = read_csv(batch1)
    shortlist, _ = read_csv(phase6b2_dir / "priority_shortlist.csv")
    evidence_rows, _ = read_csv(phase6b2_dir / "candidate_evidence_registry.csv")
    shortlist_by_id = {r["candidate_id"]: r for r in shortlist}
    evidence_by_id = {r["candidate_id"]: r for r in evidence_rows}
    manifest_ids = manifest[0]["candidate_ids"].split("|")
    selected_ids = manifest_ids[:50]
    if len(selected_ids) < 50:
        raise ValueError("First review batch has fewer than 50 candidates")
    batch_by_id = {r["candidate_id"]: r for r in first_batch}
    candidates = []
    evidence_records = []
    conflicts = []
    review_sheet = []
    canonical = {x.class_id: x for x in TAXONOMY}
    owners = {}
    for item in TAXONOMY:
        owners.setdefault(item.canonical_name.casefold(), item)
        for alias in item.aliases:
            owners.setdefault(alias.casefold(), item)
    for cid in selected_ids:
        if cid not in shortlist_by_id or cid not in batch_by_id:
            raise ValueError(f"Manifest candidate is missing from source records: {cid}")
        src = batch_by_id[cid]
        enriched = _source_record(src, evidence_by_id)
        candidate = {**src, **enriched, "proposed_class_id": src.get("proposed_canonical_class_id", ""),
                     "proposed_class_name": src.get("proposed_canonical_class_name", ""),
                     "priority_score": src.get("priority_score", ""),
                     "source_occurrence_count": src.get("source_occurrence_count", ""),
                     "original_source_references": src.get("original_source_references", "[]"),
                     "potential_ambiguity": src.get("ambiguity_warnings", "") or _screen_flags(src["candidate_phrase"]),
                     "human_review_status": "not_human_reviewed"}
        candidates.append(candidate)
        evidence_records.append(enriched)
        classid = candidate["proposed_class_id"]
        class_name = candidate["proposed_class_name"]
        phrase_norm = src.get("normalized_phrase", "").casefold()
        flags = _screen_flags(src["candidate_phrase"])
        existing = owners.get(phrase_norm)
        if classid:
            finding = "An existing Phase 6B-2 class mapping proposal is present; it remains inactive and requires reviewer identity verification."
            conflict_type = "existing_mapping_proposal"
        elif existing:
            finding = f"Phrase exactly matches taxonomy class {existing.class_id} ({existing.canonical_name}) lexically; this does not prove semantic equivalence."
            classid, class_name, conflict_type = existing.class_id, existing.canonical_name, "lexical_taxonomy_collision"
        elif flags != "not_determined":
            finding = "Phrase has a qualifier, tokenization, function, or possible truncation flag; no class assignment inferred."
            conflict_type = "phrase_ambiguity_screen"
        else:
            finding = "No automated equivalence or conflict determination; reviewer assessment remains required."
            conflict_type = "not_assessed"
        conflicts.append({"candidate_id": cid, "candidate_phrase": src["candidate_phrase"], "proposed_class_id": classid,
                          "proposed_class_name": class_name, "conflict_type": conflict_type, "finding": finding,
                          "ambiguity_flags": flags, "evidence_source_id": enriched["evidence_source_id"], "status": "proposal_only_not_activated"})
        row = {field: "" for field in DECISION_FIELDS}
        row.update(candidate_id=cid, candidate_phrase=src["candidate_phrase"])
        row.update({"normalized_phrase": src.get("normalized_phrase", ""), "discovery_category": src.get("discovery_category", ""),
                    "proposed_ingredient_identity": src.get("proposed_ingredient_identity", ""),
                    "proposed_class_id": candidate["proposed_class_id"], "proposed_class_name": candidate["proposed_class_name"],
                    "priority_score": src.get("priority_score", ""), "source_occurrence_count": src.get("source_occurrence_count", ""),
                    "original_source_references": candidate["original_source_references"], "evidence_source_id": enriched["evidence_source_id"],
                    "source_organization": enriched["source_organization"], "source_url": enriched["source_url"],
                    "evidence_type": enriched["evidence_type"], "evidence_summary": enriched["evidence_summary"],
                    "matching_terminology": enriched["matching_terminology"], "evidence_limitations": enriched["evidence_limitations"],
                    "date_checked": enriched["date_checked"], "evidence_status": enriched["evidence_status"],
                    "potential_ambiguity": candidate["potential_ambiguity"], "human_review_status": "not_human_reviewed"})
        review_sheet.append(row)

    examples, _ = read_csv(examples_path)
    source_examples = [r for r in examples if str(r.get("is_synthetic", "")).casefold() == "false" and r.get("source_type") == "source_derived"]
    example_template = []
    for row in source_examples[:50]:
        example_template.append({"example_id": row.get("candidate_id", ""), "original_ingredient_label_text": row.get("ingredient_text", ""),
            "normalized_text": row.get("normalized_text", ""), "proposed_canonical_class_id": row.get("canonical_class_id", ""),
            "proposed_canonical_class": row.get("canonical_name", ""),
            "source_provenance": row.get("contributor_provenance") or row.get("provenance_records", ""),
            "source_dataset": row.get("source_dataset", ""), "source_row_id": row.get("source_row_id", ""),
            "source_file_hash": (row.get("source_reference", "").removeprefix("sha256:") if row.get("source_reference", "").startswith("sha256:") else ""), "label_method": row.get("label_method", ""), "validation_status": row.get("validation_status", ""),
            "existing_review_status": row.get("review_status", "not_human_reviewed"), "reviewer_confirmed_class": "",
            "reviewer_decision": "", "reviewer_identity": "", "review_date": "", "justification": "", "review_attestation_reference": ""})
    output_dir.mkdir(parents=True)
    write_csv(output_dir / "pilot_candidates.csv", candidates, list(candidates[0]))
    write_csv(output_dir / "pilot_evidence_registry.csv", evidence_records, EVIDENCE_FIELDS)
    write_csv(output_dir / "pilot_taxonomy_conflicts.csv", conflicts, CONFLICT_FIELDS)
    write_csv(output_dir / "pilot_review_sheet.csv", review_sheet, PILOT_FIELDS)
    write_csv(output_dir / "ingredient_example_review_template.csv", example_template, EXAMPLE_FIELDS)
    evidence_counts = Counter(r["evidence_status"] for r in evidence_records)
    exact_terms = sum(r["evidence_type"] in {"exact_terminology", "regulatory_nomenclature", "identity_and_terminology"} for r in evidence_records)
    identity = sum(r["evidence_type"] in {"identity_and_synonym"} for r in evidence_records)
    report = {"pipeline_version": "FoodLence V4 Phase 6B-4", "pilot_size": len(candidates), "pilot_selection": "First 50 candidate IDs in the first Phase 6B-3 manifest batch, in manifest order.",
              "first_batch_count": len(manifest_ids), "all_candidates_from_phase6b2_shortlist": all(x["candidate_id"] in shortlist_by_id for x in candidates),
              "candidate_ids_and_priority_scores_preserved": all(x["candidate_id"] == batch_by_id[x["candidate_id"]]["candidate_id"] and x["priority_score"] == batch_by_id[x["candidate_id"]]["priority_score"] for x in candidates),
              "evidence_status_counts": dict(sorted(evidence_counts.items())), "exact_terminology_evidence_count": exact_terms,
              "identity_or_synonym_evidence_count": identity, "insufficient_evidence_count": evidence_counts.get("insufficient_evidence", 0),
              "not_checked_count": evidence_counts.get("not_checked", 0), "evidence_record_count": len(evidence_records),
              "traceable_source_url_count": sum(bool(r["source_url"]) for r in evidence_records),
              "taxonomy_conflict_record_count": len(conflicts), "proposal_only_no_taxonomy_changes": True,
              "vocabulary_reviewer_rows": len(review_sheet), "reviewer_controlled_fields_blank": all(not row[f] for row in review_sheet for f in ("reviewer_decision", "reviewer_identifier", "review_date", "reviewer_justification", "reviewed_canonical_class_id", "reviewed_canonical_name", "reviewed_category", "relationship_type", "evidence_support_type", "evidence_references")),
              "ingredient_example_template_rows": len(example_template), "all_example_review_fields_blank": all(not row[f] for row in example_template for f in ("reviewer_confirmed_class", "reviewer_decision", "reviewer_identity", "review_date", "justification", "review_attestation_reference")),
              "example_template_excludes_synthetic_rows": True, "no_approval_or_integration_performed": True,
              "source_hashes": {str(p): sha256_file(p) for p in [phase6b2_dir / "priority_shortlist.csv", phase6b2_dir / "candidate_evidence_registry.csv", phase6b3_dir / "review_manifest.csv", batch1, examples_path, examples_path.parent / "ingredients_train.csv", examples_path.parent / "ingredients_validation.csv", examples_path.parent / "ingredients_test.csv", Path(__file__).with_name("taxonomy.py")] if p.exists()},
              "checked_date": CHECKED,
              "limitations": ["Research was a focused pilot pass, not a complete regulatory or scientific review of all 50 candidates.", "Several source phrases appear compound, qualifier-heavy, or truncated; the heuristic flags are triage aids only.", "A regulatory or terminology listing does not establish use authorization for every purpose or validate a source product label.", "No candidate was approved, integrated, or marked human reviewed."]}
    (output_dir / "pilot_evidence_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "pilot_evidence_report.md").write_text(_report_md(report), encoding="utf-8")
    (output_dir / "pilot_reviewer_guide.md").write_text(_guide(), encoding="utf-8")
    return report


def _report_md(r: dict) -> str:
    return ("# Phase 6B-4 pilot evidence report\n\n" +
            f"- Pilot candidates: {r['pilot_size']} (first 50 from the first manifest batch of {r['first_batch_count']})\n" +
            f"- Exact terminology/context evidence: {r['exact_terminology_evidence_count']}\n" +
            f"- Identity or synonym evidence: {r['identity_or_synonym_evidence_count']}\n" +
            f"- Evidence statuses: `{json.dumps(r['evidence_status_counts'], sort_keys=True)}`\n" +
            f"- Taxonomy conflict/ambiguity screening rows: {r['taxonomy_conflict_record_count']} (all proposal-only)\n" +
            f"- Source URLs: {r['traceable_source_url_count']}\n" +
            f"- Ingredient-example review template rows: {r['ingredient_example_template_rows']}\n\n"+
            "No approvals or taxonomy changes were made. Evidence availability is not human review, and cited regulatory records do not establish authorization for every use. See `pilot_reviewer_guide.md` for handling instructions.\n")


def _guide() -> str:
    return """# Pilot reviewer guide

## Vocabulary candidate review

1. Read the original phrase and source references. Decide whether the phrase is a substance, a mixture, a functional description, a processing qualifier, or a truncated expression.
2. Open each source URL and verify its title, organization, specific term, and current context. Record only the specific evidence that source supports; a name in a reference does not by itself establish equivalence, use authorization, or a correct FoodLence label.
3. Compare identity and specificity with the proposed class. Use `approve_existing_class_alias` only when the cited evidence supports same-substance identity and the phrase is not a compound or broader/narrower substance. Use a new-concept decision only after confirming it is distinct from existing classes. Otherwise use `requires_more_evidence`, `defer`, or `reject` with reasons.
4. Leave unsupported or ambiguous candidates unresolved. Preserve candidate IDs and the evidence references. Do not edit the priority score or treat pilot evidence as approval.
5. Enter reviewer identity, ISO date, decision, justification, relationship/category, support type, and exact evidence URLs in their dedicated fields. A decision CSV is still a claim until separately attested under the Phase 6B-3 workflow.

## Illustrations only — not actual approvals

- **Illustration: baking soda.** FDA lists “BAKING SODA (SODIUM BICARBONATE)” as another name for sodium bicarbonate. A reviewer would still check that each source occurrence means the pure substance and not a baking-powder mixture. No decision is supplied here.
- **Illustration: modified food starch.** FDA lists “FOOD STARCH, MODIFIED” as another name for “STARCH, FOOD, MODIFIED.” That broad term does not make it equivalent to modified corn starch. No decision is supplied here.

## Ingredient-example review template

The separate example-level template contains source-derived examples and existing provisional labels for review context. Its reviewer-confirmed fields are empty. Existing `not_human_reviewed` status remains intact; do not infer product-level certainty from the current provenance because source product IDs are unavailable.

The evidence pilot is not a taxonomy update, training-data update, or human-reviewed ground-truth set. After genuine review, import candidate decisions through the Phase 6B-3 process with the required independent attestation; keep example-level review records separate.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).parents[1] / "foodlence_generated_v4"
    parser.add_argument("--phase6b2-dir", type=Path, default=root / "phase6b2")
    parser.add_argument("--phase6b3-dir", type=Path, default=root / "phase6b3")
    parser.add_argument("--examples", type=Path, default=root / "phase4b_corrected" / "ingredients_all.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "phase6b4")
    args = parser.parse_args()
    print(json.dumps(build_review_pilot(args.phase6b2_dir, args.phase6b3_dir, args.output_dir, args.examples), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

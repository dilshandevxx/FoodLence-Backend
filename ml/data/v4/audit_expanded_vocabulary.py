"""Quality audit and reproducible reports for FoodLence V4 Phase 7A vocabulary."""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from .recognize_ingredients import IngredientRecognizer, normalize_lookup
from .taxonomy import TAXONOMY

ROOT = Path(__file__).resolve().parents[1] / "foodlence_generated_v4"
PHASE7A = ROOT / "phase7a"
OUT = ROOT / "phase7b"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, data: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)


def audit(output_dir: Path = OUT, phase7a: Path = PHASE7A) -> dict:
    vocabulary = rows(phase7a / "expanded_vocabulary.csv")
    examples = rows(phase7a / "accepted_automatic_examples.csv")
    unresolved = rows(phase7a / "unresolved_candidates.csv")
    output_dir.mkdir(parents=True, exist_ok=True)
    concepts: dict[str, dict] = {}
    term_groups: dict[str, list[dict]] = defaultdict(list)
    concept_terms: dict[str, set[str]] = defaultdict(set)
    for r in vocabulary:
        cid = r.get("class_id", "")
        term = r.get("term", "")
        key = normalize_lookup(r.get("normalized_term") or term)
        if key:
            term_groups[key].append(r)
        if cid and r.get("entry_kind") != "canonical_class":
            concepts.setdefault(cid, {"concept_id": cid, "concept_name": r.get("canonical_name", ""), "evidence_tier": r.get("evidence_tier", ""), "taxonomy_type": r.get("taxonomy_type", ""), "review_status": r.get("review_status", "not_human_reviewed")})
            concept_terms[cid].add(key)
    examples_by_concept: Counter[str] = Counter(r.get("proposed_class_id", "") for r in examples)
    phrases_by_concept: dict[str, set[str]] = defaultdict(set)
    source_phrases_by_concept: dict[str, set[str]] = defaultdict(set)
    for r in examples:
        phrases_by_concept[r.get("proposed_class_id", "")].add(normalize_lookup(r.get("normalized_text")))
        if r.get("source_type") == "source_derived":
            source_phrases_by_concept[r.get("proposed_class_id", "")].add(normalize_lookup(r.get("normalized_text")))
    single_phrase = sum(len(source_phrases_by_concept.get(cid, set())) <= 1 for cid in concepts)
    dist = []
    for cid, concept in sorted(concepts.items()):
        dist.append({**concept, "term_count": len(concept_terms[cid]), "example_count": examples_by_concept[cid], "distinct_observed_phrase_count": len(phrases_by_concept.get(cid, set()))})
    collisions = [{"normalized_term": key, "terms": " | ".join(sorted({r.get("term", "") for r in group})), "concept_ids": " | ".join(sorted({r.get("class_id", "") for r in group})), "entry_kinds": " | ".join(sorted({r.get("entry_kind", "") for r in group}))} for key, group in sorted(term_groups.items()) if len({r.get("class_id", "") for r in group}) > 1]
    duplicate_terms = sum(max(0, len(group) - 1) for group in term_groups.values())
    name_owners: dict[str, set[str]] = defaultdict(set)
    for cid, c in concepts.items():
        name_owners[normalize_lookup(c["concept_name"])].add(cid)
    name_collisions = sum(1 for ids in name_owners.values() if len(ids) > 1)
    lengths = [len(normalize_lookup(r.get("term"))) for r in vocabulary]
    suspicious = [r for r in vocabulary if len(normalize_lookup(r.get("term"))) > 80 or re.search(r"\d|\be\s*[- ]?\d{3,4}[a-z]?\b", r.get("term", ""), re.I) or re.search(r"[(){}\[\]<>]", r.get("term", ""))]
    compound = sum(1 for r in vocabulary if re.search(r"\b(and|or|with|containing)\b|[,;/]", r.get("term", ""), re.I))
    canonical_names = {normalize_lookup(c.canonical_name) for c in TAXONOMY}
    overlap = sum(1 for cid, c in concepts.items() if normalize_lookup(c["concept_name"]) in canonical_names)
    exact_single_phrase = sum(len(source_phrases_by_concept.get(cid, set())) == 1 for cid in concepts)
    zero_phrase = sum(len(source_phrases_by_concept.get(cid, set())) == 0 for cid in concepts)
    quality = {"provisional_concept_count": len(concepts), "concepts_with_exactly_one_source_derived_phrase": exact_single_phrase, "concepts_with_zero_source_derived_examples": zero_phrase, "concepts_with_one_or_fewer_source_derived_phrases": single_phrase, "single_example_count_including_synthetic": sum(examples_by_concept[cid] == 1 for cid in concepts), "multiple_terms_same_concept_count": sum(len(v) > 1 for v in concept_terms.values()), "normalized_terms_mapping_to_multiple_concepts_count": len(collisions), "duplicate_normalized_term_rows_beyond_first": duplicate_terms, "potentially_redundant_concept_name_collisions": name_collisions, "canonical_provisional_name_overlap_count": overlap, "compound_expression_term_count": compound, "very_long_or_numeric_or_punctuated_term_count": len(suspicious), "numeric_or_e_number_like_term_count": sum(bool(re.search(r"\d|\be\s*[- ]?\s*\d{3,4}[a-z]?\b", r.get("term", ""), re.I)) for r in vocabulary), "maximum_term_length": max(lengths, default=0), "taxonomy_class_count": len(TAXONOMY), "examples_per_concept_median": sorted(examples_by_concept[cid] for cid in concepts)[len(concepts)//2] if concepts else 0, "scientific_identity_established": False, "human_reviewed_examples": 0, "limitations": ["Counts describe accepted Phase 7A source-derived rows; they do not establish independent identity.", "String and count patterns flag review candidates only; they do not establish synonymy or chemical identity.", "Vocabulary-derived coverage is in-sample and is not independent classification accuracy."]}
    write_csv(output_dir / "concept_distribution.csv", dist, ["concept_id", "concept_name", "evidence_tier", "taxonomy_type", "review_status", "term_count", "example_count", "distinct_observed_phrase_count"])
    write_csv(output_dir / "possible_duplicate_concepts.csv", collisions, ["normalized_term", "terms", "concept_ids", "entry_kinds"])
    write_csv(output_dir / "ambiguous_terms.csv", collisions, ["normalized_term", "terms", "concept_ids", "entry_kinds"])
    (output_dir / "vocabulary_quality_report.json").write_text(json.dumps(quality, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (output_dir / "vocabulary_quality_report.md").write_text("# FoodLence V4 Phase 7B Vocabulary Quality\n\n" + "\n".join(f"- **{k.replace('_',' ').capitalize()}:** {v}" for k,v in quality.items() if not isinstance(v, list)) + "\n\n## Limitations\n\n" + "\n".join(f"- {x}" for x in quality["limitations"]) + "\n", encoding="utf-8")

    recognizer = IngredientRecognizer(phase7a / "expanded_vocabulary.csv", phase7a / "accepted_automatic_examples.csv")
    source_phrases = sorted({normalize_lookup(r.get("normalized_text")) for r in examples if r.get("source_type") == "source_derived" and normalize_lookup(r.get("normalized_text"))} | {normalize_lookup(r.get("normalized_phrase") or r.get("candidate_phrase")) for r in unresolved if normalize_lookup(r.get("normalized_phrase") or r.get("candidate_phrase"))})
    start = time.perf_counter()
    source_results = [recognizer.recognize(p, False) for p in source_phrases]
    source_lookup_seconds = time.perf_counter() - start
    vocab_phrases = sorted({normalize_lookup(r.get("normalized_term") or r.get("term")) for r in vocabulary if normalize_lookup(r.get("normalized_term") or r.get("term"))})
    vocab_results = [recognizer.recognize(p, False) for p in vocab_phrases]
    observed_example = next((r.get("normalized_text", "") for r in examples if r.get("source_type") == "source_derived" and r.get("normalized_text")), "")
    synthetic_example = next((r.get("original_text", "") for r in examples if r.get("is_synthetic", "").casefold() == "true"), "")
    ambiguous_example = collisions[0]["normalized_term"] if collisions else ""
    unresolved_example = unresolved[0].get("candidate_phrase", "") if unresolved else ""
    sample_inputs = ["wheat flour", "food starch modified", observed_example, unresolved_example, ambiguous_example, synthetic_example, "E 202", ""]
    samples = [recognizer.recognize(p) for p in sample_inputs]
    write_csv(output_dir / "sample_recognition_results.csv", [{**r, "source_provenance": json.dumps(r["source_provenance"], ensure_ascii=False), "ambiguity_details": json.dumps(r["ambiguity_details"], ensure_ascii=False)} for r in samples], list(samples[0]))
    def coverage(results):
        count = Counter(r["match_status"] for r in results)
        return {"input_count": len(results), "exact_match_count": len(results)-count["unresolved"]-count["ambiguous"], "ambiguous_count": count["ambiguous"], "unknown_count": count["unresolved"], "status_counts": dict(sorted(count.items()))}
    coverage_report = {"known_vocabulary_phrase_coverage": coverage(vocab_results), "source_observed_phrase_coverage": coverage(source_results), "evidence_tier_coverage": {tier: dict(Counter(r["match_status"] for r in source_results if r["evidence_tier"] == tier)) for tier in ("A", "B", "C", "D")}, "canonical_vs_provisional_match_counts": {"canonical": sum(r["match_status"] == "canonical_exact" for r in source_results), "provisional_or_evidence_supported": sum(r["match_status"] in {"provisional_exact", "evidence_supported_exact"} for r in source_results), "synthetic": sum(r["match_status"] == "synthetic_exact" for r in source_results)}, "lookup_latency_seconds_total": source_lookup_seconds, "lookup_latency_microseconds_per_phrase": source_lookup_seconds * 1_000_000 / max(1, len(source_phrases)), "benchmark_independent": False, "accuracy_precision_recall_f1": None, "interpretation": "These are deterministic in-sample exact-lookup coverage measures, not independent classification accuracy.", "recognition_status_categories": sorted({"canonical_exact", "evidence_supported_exact", "provisional_exact", "synthetic_exact", "ambiguous", "unresolved"})}
    (output_dir / "recognition_coverage_report.json").write_text(json.dumps(coverage_report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (output_dir / "recognition_coverage_report.md").write_text("# Recognition Coverage\n\n" + json.dumps(coverage_report, indent=2, ensure_ascii=False) + "\n\nNo independent human-reviewed benchmark exists; accuracy, precision, recall, and F1 cannot be established.\n", encoding="utf-8")
    (output_dir / "recognition_limitations.md").write_text("# Recognition limitations\n\n- Exact matches only; no fuzzy matching or automatic identity inference.\n- Exact provisional term matches are not scientific verification.\n- Canonical taxonomy entries remain scientifically unverified.\n- Unresolved means not present in the vocabulary; it is not an allergen-free or safe result.\n- No independent human-reviewed benchmark exists, so accuracy, precision, recall, and F1 are not established.\n- All examples retain `not_human_reviewed`; the allergen dataset is separate.\n", encoding="utf-8")
    return {"quality": quality, "coverage": coverage_report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase7a", type=Path, default=PHASE7A)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(audit(args.output_dir, args.phase7a), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

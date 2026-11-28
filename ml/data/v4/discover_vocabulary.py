"""Conservative, evidence-preserving discovery of unmatched food phrases.

The categories and scores in this module are triage aids only. They never
create taxonomy mappings or claim scientific verification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from .extract_sources import normalize
from .taxonomy import TAXONOMY

CATEGORIES = (
    "possible_existing_class_alias", "possible_new_ingredient", "possible_additive",
    "compound_ingredient_expression", "product_or_description", "ambiguous", "invalid_or_noise",
)
FIELDS = [
    "candidate_phrase", "normalized_phrase", "frequency", "source_references",
    "discovery_category", "suggested_existing_class_id", "suggested_existing_class_name",
    "suggested_new_class_name", "candidate_evidence", "evidence_source",
    "verification_status", "review_status", "priority_score", "priority_rationale",
    "character_count", "word_count", "pattern_flags",
]
REVIEW_STATUS = "not_human_reviewed"
VERIFICATION_STATUS = "unverified"
_E_NUMBER = re.compile(r"(?<![a-z0-9])e\s*[- ]?\s*\d{3,4}[a-z]{0,2}(?![a-z0-9])", re.I)
_ADDITIVE_CUE = re.compile(r"\b(acid|sorbate|benzoate|propionate|nitrite|nitrate|phosphate|phosphoric|citrate|carbonate|chloride|sulphite|sulfite|lecithin|gum|silica|silicon dioxide|preservative|colour|color|emulsifier|stabilizer|stabiliser|sweetener|antioxidant)\b", re.I)
_DESCRIPTION_CUE = re.compile(r"\b(contains|may contain|product|preparation|flavou?r|suitable for|made with|with added|ingredients?)\b", re.I)
_FOOD_FORM = re.compile(r"\b(flour|powder|oil|starch|protein|concentrate|extract|juice|syrup|butter|seed|leaf|root|peel|fibre|fiber|paste|puree|purée)\b", re.I)
_COMPOUND_CUE = re.compile(r",|;|\+|/|&|\b(?:and|or)\b", re.I)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_candidate(value: str | None) -> str:
    """NFKC/casefold/space and dash normalization shared with extraction."""
    return normalize(unicodedata.normalize("NFKC", value or ""))


def _category(phrase: str, alias_index: dict[str, set], max_length: int = 160) -> tuple[str, str, str, str, list[str]]:
    text = phrase.strip()
    folded = normalize_candidate(text)
    flags = []
    if not folded:
        return "invalid_or_noise", "empty phrase", "", "", ["empty"]
    if len(folded) > max_length:
        flags.append("overlong")
    if not re.search(r"[a-z]", folded):
        flags.append("no_latin_letters")
    if re.search(r"https?://|www\.|@\w+\.", folded):
        flags.append("url_or_email_like")
    visible = [c for c in folded if not c.isspace()]
    unusual = sum(not (c.isalnum() or c in "-+/,().%&'’") for c in visible)
    if visible and unusual / len(visible) > 0.18:
        flags.append("high_symbol_ratio")
    if any(ord(c) > 127 for c in folded):
        flags.append("non_ascii_or_language_signal")
    if "\ufffd" in folded:
        flags.extend(["replacement_character", "ocr_or_encoding_corruption_signal"])
    if folded.count("(") != folded.count(")") or folded.count("[") != folded.count("]"):
        flags.append("unbalanced_delimiter")
    if _E_NUMBER.search(folded):
        flags.append("e_number_like_pattern")
    if re.search(r"\d", folded) and not _E_NUMBER.search(folded):
        flags.append("numeric_or_code_like")
    if _COMPOUND_CUE.search(folded):
        flags.append("compound_delimiter")

    alias_hits = alias_index.get(folded, set())
    if len(alias_hits) == 1:
        class_id, class_name = next(iter(alias_hits))
        return "possible_existing_class_alias", "exact normalized match to an explicitly declared taxonomy alias; still requires semantic review", class_id, class_name, flags
    if len(alias_hits) > 1:
        return "ambiguous", "exact normalized alias is declared by multiple taxonomy classes", "", "", flags + ["alias_collision"]
    if flags and ("empty" in flags or "overlong" in flags or "no_latin_letters" in flags or "url_or_email_like" in flags or "high_symbol_ratio" in flags or "replacement_character" in flags):
        return "invalid_or_noise", "fails conservative text-quality heuristics", "", "", flags
    if _COMPOUND_CUE.search(folded):
        return "compound_ingredient_expression", "contains a list/conjunction delimiter; components are not split or mapped", "", "", flags
    if _DESCRIPTION_CUE.search(folded):
        return "product_or_description", "contains product or descriptive wording", "", "", flags
    if _E_NUMBER.search(folded) or _ADDITIVE_CUE.search(folded):
        is_code = bool(_E_NUMBER.search(folded))
        cue = "E-number-like token" if is_code else "additive-related lexical cue"
        suggestion = "" if is_code else folded
        return "possible_additive", f"{cue}; lexical cue only, no regulatory mapping inferred", "", suggestion, flags
    if any(c in folded for c in "()[]") or re.search(r"\d", folded):
        return "ambiguous", "parenthetical or numeric text needs contextual review", "", "", flags
    words = re.findall(r"[a-z]+(?:['’][a-z]+)?", folded)
    if 1 <= len(words) <= 4 and re.fullmatch(r"[a-z][a-z\s'’-]*", folded):
        rationale = "standalone short alphabetic phrase; candidate only, not a verified ingredient"
        if _FOOD_FORM.search(folded):
            rationale = "standalone phrase with a food-form term; candidate only, not a verified ingredient"
        return "possible_new_ingredient", rationale, "", folded, flags
    return "ambiguous", "insufficient conservative lexical evidence for a narrower discovery category", "", "", flags


def priority_score(frequency: int, category: str, phrase: str, underrepresented_alias: bool = False) -> tuple[int, str]:
    """Deterministic review triage score, explicitly not a confidence score."""
    frequency_points = min(50, int(10 * math.log2(max(1, frequency))))
    candidate_points = 30 if category in {"possible_existing_class_alias", "possible_new_ingredient", "possible_additive"} else 12 if category == "compound_ingredient_expression" else 0
    reviewability_points = 20 if 0 < len(phrase) <= 80 and category != "invalid_or_noise" else 0
    representation_points = 10 if underrepresented_alias else 0
    score = min(100, frequency_points + candidate_points + reviewability_points + representation_points)
    return score, f"frequency={frequency_points}; standalone_candidate={candidate_points}; reviewability={reviewability_points}; underrepresented_known_class={representation_points}; not scientific confidence"


def _write(path: Path, rows: list[dict], fields=FIELDS) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def discover_vocabulary(input_path: Path, output_dir: Path, taxonomy=TAXONOMY, taxonomy_distribution_path: Path | None = None) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing discovery output: {output_dir}")
    taxonomy_by_id = {item.class_id: item for item in taxonomy}
    alias_index: dict[str, set] = defaultdict(set)
    for item in taxonomy:
        for alias in item.aliases:
            normalized_alias = normalize_candidate(alias)
            if normalized_alias:
                alias_index[normalized_alias].add((item.class_id, item.canonical_name))
    class_train_counts = {}
    if taxonomy_distribution_path and taxonomy_distribution_path.exists():
        with taxonomy_distribution_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                class_train_counts[row.get("canonical_class_id", "")] = int(row.get("train_examples") or 0)

    if not input_path.exists():
        raise FileNotFoundError(input_path)
    input_hash = file_sha256(input_path)
    groups: dict[str, dict] = {}
    total = malformed_rows = 0
    phase2_normalized_phrases: set[str] = set()
    required = {"candidate_id", "ingredient_text", "normalized_text", "source_dataset", "source_file_hash", "source_row_id", "source_text"}
    try:
        with input_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"unmatched CSV missing required columns: {sorted(required - set(reader.fieldnames or []))}")
            for row in reader:
                total += 1
                original = (row.get("ingredient_text") or "").strip()
                phase2_normalized_phrases.add(row.get("normalized_text") or "")
                phrase = normalize_candidate(row.get("normalized_text") or original)
                malformed = not original or not row.get("candidate_id") or not row.get("source_row_id") or row.get(None) is not None
                malformed_rows += int(malformed)
                key = phrase
                item = groups.setdefault(key, {"variants": Counter(), "references": [], "occurrences": 0, "malformed": False})
                item["variants"][original] += 1
                item["occurrences"] += 1
                item["malformed"] = item["malformed"] or malformed
                item["references"].append({
                    "candidate_id": row.get("candidate_id", ""), "source_dataset": row.get("source_dataset", ""),
                    "source_file_hash": row.get("source_file_hash", ""), "source_row_id": row.get("source_row_id", ""),
                    "source_text": row.get("source_text", ""), "ingredient_text": row.get("ingredient_text", ""),
                    "malformed_extra_fields": row.get(None, []),
                })
    except csv.Error as exc:
        raise ValueError(f"malformed unmatched CSV: {exc}") from exc

    if malformed_rows:
        # Retained and categorized, rather than dropped, with stable source references.
        pass
    class_rows = []
    for phrase, item in groups.items():
        candidate_phrase = sorted(item["variants"].items(), key=lambda pair: (-pair[1], pair[0].casefold(), pair[0]))[0][0]
        category, evidence, suggested_id, suggested_name, flags = _category(phrase, alias_index)
        if item["malformed"]:
            category, evidence, suggested_id, suggested_name = "invalid_or_noise", "one or more source rows lack required occurrence identifiers or ingredient text", "", ""
            flags = sorted(set(flags + ["malformed_source_record"]))
        if suggested_id and class_train_counts.get(suggested_id, 0) < 2:
            underrepresented = True
        else:
            underrepresented = False
        score, score_rationale = priority_score(item["occurrences"], category, phrase, underrepresented)
        references = sorted(item["references"], key=lambda ref: (ref["source_dataset"], ref["source_row_id"], ref["candidate_id"]))
        evidence_source = "; ".join(sorted({f"{r['source_dataset']} row {r['source_row_id']} (sha256:{r['source_file_hash']})" for r in references}))
        class_rows.append({
            "candidate_phrase": candidate_phrase, "normalized_phrase": phrase, "frequency": item["occurrences"],
            "source_references": json.dumps(references, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "discovery_category": category, "suggested_existing_class_id": suggested_id,
            "suggested_existing_class_name": suggested_name if suggested_id else "",
            "suggested_new_class_name": suggested_name if not suggested_id else "",
            "candidate_evidence": evidence, "evidence_source": evidence_source,
            "verification_status": VERIFICATION_STATUS, "review_status": REVIEW_STATUS,
            "priority_score": score, "priority_rationale": score_rationale,
            "character_count": len(phrase), "word_count": len(phrase.split()), "pattern_flags": ";".join(sorted(set(flags))),
        })
    class_rows.sort(key=lambda row: (-int(row["priority_score"]), -int(row["frequency"]), row["normalized_phrase"]))
    by_category = {category: [row for row in class_rows if row["discovery_category"] == category] for category in CATEGORIES}
    output_dir.mkdir(parents=True)
    _write(output_dir / "vocabulary_candidates.csv", class_rows)
    category_files = {
        "possible_existing_aliases.csv": "possible_existing_class_alias",
        "possible_new_ingredients.csv": "possible_new_ingredient",
        "possible_additives.csv": "possible_additive",
        "compound_expressions.csv": "compound_ingredient_expression",
        "ambiguous_candidates.csv": "ambiguous",
        "rejected_noise.csv": "invalid_or_noise",
    }
    for filename, category in category_files.items():
        _write(output_dir / filename, by_category[category])
    review_rows = [row for row in class_rows if row["discovery_category"] != "invalid_or_noise"]
    _write(output_dir / "human_review_queue.csv", review_rows)

    frequencies = [int(row["frequency"]) for row in class_rows]
    occurrence_categories = Counter()
    for row in class_rows:
        occurrence_categories[row["discovery_category"]] += int(row["frequency"])
    lengths = Counter()
    punctuation = Counter()
    punctuation_patterns = Counter()
    length_occurrences = Counter()
    prefix = Counter()
    suffix = Counter()
    numbers = codes = compound_count = non_ascii_count = 0
    ocr_corruption_count = unbalanced_delimiter_count = 0
    top = []
    for row in class_rows:
        phrase = row["normalized_phrase"]
        n = len(phrase)
        lengths["0"] += int(n == 0)
        lengths["1-20"] += int(1 <= n <= 20)
        lengths["21-40"] += int(21 <= n <= 40)
        lengths["41-80"] += int(41 <= n <= 80)
        lengths["81+"] += int(n > 80)
        for bucket, condition in (("0", n == 0), ("1-20", 1 <= n <= 20), ("21-40", 21 <= n <= 40), ("41-80", 41 <= n <= 80), ("81+", n > 80)):
            length_occurrences[bucket] += int(condition) * int(row["frequency"])
        for char in re.findall(r"[^\w\s]", phrase):
            punctuation[char] += int(row["frequency"])
        for pattern, regex in (("parentheses", r"[()]"), ("brackets", r"[\[\]]"), ("comma", r","), ("semicolon", r";"), ("hyphen", r"-"), ("slash", r"/"), ("plus", r"\+"), ("ampersand", r"&"), ("period", r"\."), ("colon", r":")):
            if re.search(regex, phrase):
                punctuation_patterns[pattern] += int(row["frequency"])
        words = phrase.split()
        if words:
            prefix[words[0]] += int(row["frequency"])
            suffix[words[-1]] += int(row["frequency"])
        numbers += int(bool(re.search(r"\d", phrase)))
        codes += int(bool(_E_NUMBER.search(phrase)))
        compound_count += int(row["discovery_category"] == "compound_ingredient_expression")
        non_ascii_count += int(any(ord(c) > 127 for c in phrase))
        ocr_corruption_count += int("\ufffd" in phrase)
        unbalanced_delimiter_count += int(phrase.count("(") != phrase.count(")") or phrase.count("[") != phrase.count("]"))
        if row["discovery_category"] in {"possible_existing_class_alias", "possible_new_ingredient", "possible_additive"}:
            top.append({"phrase": phrase, "frequency": row["frequency"], "category": row["discovery_category"], "priority_score": row["priority_score"]})
    top.sort(key=lambda item: (-int(item["frequency"]), item["phrase"]))
    top = top[:100]
    sorted_freq = sorted(frequencies)
    median = sorted_freq[(len(sorted_freq) - 1) // 2] if sorted_freq else 0
    report = {
        "pipeline_version": "FoodLence V4 Phase 6B-1",
        "input_file": str(input_path.as_posix()), "input_sha256": input_hash,
        "taxonomy_modified": False, "authoritative_ingredient_dataset_modified": False,
        "source_occurrences_analyzed": total, "unique_normalized_candidate_phrases": len(class_rows),
        "unique_phase2_normalized_phrases_before_discovery_normalization": len(phase2_normalized_phrases),
        "phrase_groups_merged_by_discovery_normalization": len(phase2_normalized_phrases) - len(class_rows),
        "malformed_source_occurrences_retained": malformed_rows,
        "output_candidate_frequency_sum": sum(int(row["frequency"]) for row in class_rows),
        "input_output_occurrence_counts_reconcile": total == sum(int(row["frequency"]) for row in class_rows),
        "candidate_counts_by_category_unique_phrases": {k: len(by_category[k]) for k in CATEGORIES},
        "candidate_counts_by_category_occurrences": {k: occurrence_categories[k] for k in CATEGORIES},
        "frequency_summary": {"mean": (sum(frequencies) / len(frequencies) if frequencies else 0), "median": median, "maximum": max(frequencies, default=0), "single_occurrence_phrases": sum(v == 1 for v in frequencies)},
        "phrase_length_character_buckets_unique_phrases": dict(lengths),
        "phrase_length_character_buckets_occurrences": dict(length_occurrences),
        "common_prefixes_by_occurrence": prefix.most_common(20), "common_suffixes_by_occurrence": suffix.most_common(20),
        "punctuation_counts_by_occurrence": dict(sorted(punctuation.items())),
        "punctuation_pattern_counts_by_occurrence": dict(sorted(punctuation_patterns.items())),
        "numeric_or_code_like_unique_phrases": numbers, "e_number_like_unique_phrases": codes,
        "compound_expression_unique_phrases": compound_count,
        "non_ascii_or_possible_language_variation_phrases": non_ascii_count,
        "ocr_or_encoding_corruption_signal_phrases": ocr_corruption_count,
        "unbalanced_delimiter_phrases": unbalanced_delimiter_count,
        "top_recurring_plausible_candidates": top,
        "human_review_queue_size": len(review_rows),
        "review_status_distribution": {REVIEW_STATUS: len(class_rows)},
        "verification_status_distribution": {VERIFICATION_STATUS: len(class_rows)},
        "priority_score_semantics": "Deterministic triage only; frequency and lexical heuristics are not scientific confidence or proof of ingredient identity.",
        "normalization_rules": ["Unicode NFKC", "casefold", "whitespace collapse", "dash normalization shared with Phase 2; punctuation otherwise retained"],
        "classification_limitations": ["Categories are candidate triage only, not verified food-science labels.", "No string-similarity mapping, taxonomy additions, aliases, E-number mappings, or canonical IDs are assigned.", "Non-ASCII text is only a language-variation signal; language is not identified.", "Open Food Facts candidate occurrence references preserve source file hash and row ID; frequency is not evidence of correctness."],
    }
    (output_dir / "vocabulary_discovery_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(output_dir / "vocabulary_discovery_report.md", report, by_category)
    return report


def _write_markdown(path: Path, report: dict, by_category: dict) -> None:
    lines = ["# FoodLence V4 vocabulary discovery", "", f"- Source unmatched occurrences: {report['source_occurrences_analyzed']}",
             f"- Unique normalized phrases: {report['unique_normalized_candidate_phrases']}",
             f"- Input/output occurrence counts reconcile: {report['input_output_occurrence_counts_reconcile']}", "", "## Candidate categories", "",
             "| Category | Unique phrases | Occurrences |", "|---|---:|---:|"]
    for category in CATEGORIES:
        lines.append(f"| {category} | {report['candidate_counts_by_category_unique_phrases'][category]} | {report['candidate_counts_by_category_occurrences'][category]} |")
    lines += ["", "## Most frequent plausible candidate phrases", "", "| Phrase | Frequency | Category | Priority |", "|---|---:|---|---:|"]
    for item in report["top_recurring_plausible_candidates"][:25]:
        lines.append(f"| {item['phrase'].replace('|', '\\|')} | {item['frequency']} | {item['category']} | {item['priority_score']} |")
    lines += ["", "Priority is a deterministic review-triage score, not scientific confidence. Candidate labels are unverified and not human-reviewed.",
              "No canonical mappings, aliases, or E-number relationships were added. See the CSV source references for source file hashes and row IDs.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).parents[1] / "foodlence_generated_v4"
    parser.add_argument("--input", type=Path, default=root / "phase2" / "unmatched_candidates.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "phase6b1")
    parser.add_argument("--class-distribution", type=Path, default=root / "final_reports" / "v4_class_distribution.csv")
    args = parser.parse_args()
    print(json.dumps(discover_vocabulary(args.input, args.output_dir, taxonomy_distribution_path=args.class_distribution), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

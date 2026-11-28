"""Conservative source phrase extraction with explicit provenance."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
import re
from collections import Counter, defaultdict
from pathlib import Path

from .taxonomy import TAXONOMY, TaxonomyClass

FIELDS = ["candidate_id", "ingredient_text", "normalized_text", "source_dataset", "source_file_hash", "source_row_id", "source_text", "extraction_method", "is_synthetic", "label_method", "canonical_class_id", "validation_status", "validation_reason", "review_status"]
DEFAULT_ROOT = Path(__file__).parents[1]


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").casefold()
    value = value.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"\s*[-‐‑–—]\s*", " ", value)
    value = re.sub(r"\s+", " ", value.strip())
    return value


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def taxonomy_index(classes: tuple[TaxonomyClass, ...]):
    index = defaultdict(set)
    valid_ids = {item.class_id for item in classes}
    for item in classes:
        index[normalize(item.canonical_name)].add(item.class_id)
        for alias in item.aliases:
            if normalize(alias):
                index[normalize(alias)].add(item.class_id)
    return index, valid_ids


def match_candidate(text: str, index: dict, valid_ids: set[str]) -> dict:
    hits = index.get(normalize(text), set())
    if any(class_id not in valid_ids for class_id in hits):
        return {"canonical_class_id": "", "validation_status": "invalid", "label_method": "", "validation_reason": "taxonomy contains invalid class reference"}
    if len(hits) > 1:
        return {"canonical_class_id": "", "validation_status": "ambiguous", "label_method": "", "validation_reason": "exact alias maps to multiple classes"}
    if len(hits) == 1:
        class_id = next(iter(hits))
        return {"canonical_class_id": class_id, "validation_status": "matched_provisional", "label_method": "exact_taxonomy_match", "validation_reason": "exact canonical name or explicitly declared alias after safe Unicode/case/whitespace/hyphen normalization; provisional only"}
    return {"canonical_class_id": "", "validation_status": "unmatched", "label_method": "", "validation_reason": "no exact canonical name or declared alias"}


def extract_sources(input_path: Path, output_dir: Path, classes: tuple[TaxonomyClass, ...] = TAXONOMY) -> dict:
    """Extract safe single-name rows; compound/list rows are quarantined as skipped."""
    import re
    source_hash = file_hash(input_path)
    index, valid_ids = taxonomy_index(classes)
    occurrences = defaultdict(list)
    total = skipped = parse_failures = 0
    with input_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"ingredient"}.issubset(reader.fieldnames or []):
            raise ValueError("Source CSV must contain an ingredient column")
        for row_number, row in enumerate(reader, 2):
            total += 1
            original = row.get("ingredient") or ""
            normalized = normalize(original)
            if not normalized:
                skipped += 1
                continue
            # Conservative: keep only simple phrases; never split composites heuristically.
            if len(normalized) > 100 or "," in normalized or ";" in normalized or "\n" in normalized or re.search(r"\d\s*%", normalized):
                skipped += 1
                continue
            occurrences[normalized].append((row_number, original))
    candidates = []
    for normalized in sorted(occurrences):
        for row_number, original in occurrences[normalized]:
            match = match_candidate(normalized, index, valid_ids)
            candidate_id = hashlib.sha256(f"{source_hash}:{row_number}:{normalized}".encode()).hexdigest()[:24]
            candidates.append({"candidate_id": candidate_id, "ingredient_text": original, "normalized_text": normalized,
                "source_dataset": input_path.name, "source_file_hash": source_hash, "source_row_id": str(row_number),
                "source_text": original, "extraction_method": "source_ingredient_field_simple_phrase",
                "is_synthetic": "false", **match, "review_status": "not_human_reviewed"})
    counts = Counter(row["validation_status"] for row in candidates)
    class_counts = Counter(row["canonical_class_id"] for row in candidates if row["canonical_class_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = {
        "source_candidates.csv": candidates,
        "matched_candidates.csv": [r for r in candidates if r["validation_status"] == "matched_provisional"],
        "unmatched_candidates.csv": [r for r in candidates if r["validation_status"] == "unmatched"],
        "ambiguous_candidates.csv": [r for r in candidates if r["validation_status"] in {"ambiguous", "invalid"}],
    }
    for filename, rows in groups.items():
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    report = {"source_rows_processed": total, "candidates_extracted": len(candidates),
        "unique_normalized_phrases": len(occurrences), "repeated_occurrences": len(candidates) - len(occurrences),
        "matched_candidate_count": counts["matched_provisional"], "unmatched_candidate_count": counts["unmatched"],
        "ambiguous_candidate_count": counts["ambiguous"] + counts["invalid"], "duplicate_candidate_count": len(candidates) - len(occurrences),
        "candidate_counts_per_class": dict(sorted(class_counts.items())),
        "extraction_method_distribution": {"source_ingredient_field_simple_phrase": len(candidates)},
        "source_file_hash": source_hash, "rows_skipped_compound_or_empty": skipped, "parsing_failures": parse_failures,
        "review_status": "not_human_reviewed", "matching_is_provisional": True}
    (output_dir / "extraction_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(__file__).parents[1] / "raw" / "openfoodfacts_filtered.csv")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parents[1] / "foodlence_generated_v4" / "phase2")
    args = parser.parse_args()
    print(json.dumps(extract_sources(args.input, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

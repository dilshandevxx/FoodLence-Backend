# FoodLence ML datasets

This directory contains source-data templates, reproducible dataset builders,
and local outputs for FoodLence ingredient/additive classification and
allergen detection. Keep the tasks separate: ingredient classification uses
one canonical label per phrase; allergen detection can have multiple labels.

## Dataset pipelines

### Primary development dataset: synthetic bootstrap

`foodlence_fresh/build_fresh.py` builds local synthetic development data in
`foodlence_fresh/output/`. It creates 180 vocabulary classes and synthetic
phrase variants with train, validation, and test partitions. Labels are
automatically assigned from embedded vocabulary and rules; they are **not
human-validated**. Validation and test use synthetic contexts and do not
measure real-world accuracy. Allergen examples are positive-only; missing
associations must not be treated as negatives.

Regenerate with `python ml/data/foodlence_fresh/build_fresh.py`.

### Experimental dataset: Open Food Facts weak labels

`build_foodlence_v3.py` reads `raw/openfoodfacts_filtered.csv` and
`raw/allergies_10k.csv`, then writes experimental outputs to
`foodlence_generated_v3/`. Phrase-to-self labels and unique E-number mappings
are weak supervision, not reviewed canonical annotations. Source data has no
product IDs, so phrase hashing cannot guarantee product-level split
independence. Class coverage is limited and uneven, and synthetic OCR variants
are heuristic. Source licenses and attribution are unverified; check applicable
terms before sharing or distributing data. Do not combine these outputs with
the synthetic bootstrap automatically.

Regenerate with `python ml/data/build_foodlence_v3.py`. The script refuses to
overwrite existing V3 output unless invoked with `--overwrite`.

## Inputs, outputs, and limitations

- Local source CSVs belong in `raw/`; large source files are excluded from Git.
- The synthetic builder reads no external files. V3 expects the two CSVs above.
- `profile_sources.py` inventories source CSVs; run
  `python ml/data/profile_sources.py` to refresh the local profile.
- `inspect_foodlence.py` provides a broader read-only inventory.
- Generated CSVs and reports are local artifacts and excluded from Git; keep
  builders and documentation for reproducibility.

Both builders use a fixed seed. V3 splits by normalized phrase before creating
variants, and creates variants only for training rows. This reduces phrase
variant leakage but cannot guarantee product independence without product IDs.
The synthetic builder uses separate contexts per split but shares labels and
vocabulary across splits; it is a development aid, not a benchmark.

`foodlence_generated/` and `foodlence_generated_v2/` are older experimental
outputs retained locally for comparison and are candidates for later cleanup.

## Raw OCR and reviewed annotation templates

Task 02 stores OCR observations separately from reviewed training labels.

## Raw OCR: `raw/ocr_samples.csv`

Each row is one OCR result from one label capture. Keep the original OCR text unchanged.

| Column | Required | Meaning |
|---|---:|---|
| `sample_id` | yes | Stable unique identifier, for example `OCR-000001`. |
| `source_id` | yes | Product or package capture identifier. Used to prevent data leakage. |
| `ocr_text` | yes | Exact text returned by Google ML Kit. |
| `product_type` | yes | Product category, such as biscuit, milk, or sauce. |
| `country_origin` | yes | Local or imported product origin. |
| `capture_condition` | yes | Lighting, curved package, foil, crumpled box, or other condition. |
| `capture_date` | no | Date of image capture in ISO format. |
| `notes` | no | Collection notes; never alter `ocr_text` here. |

## Annotated data: `annotated/ocr_ingredients.csv`

Each row is one ingredient mention reviewed against the canonical knowledge base.

| Column | Required | Meaning |
|---|---:|---|
| `sample_id` | yes | Links to `raw/ocr_samples.csv`. |
| `source_id` | yes | Must match the raw record and remain grouped during splitting. |
| `text` | yes | Ingredient phrase as observed or segmented from OCR. |
| `label` | yes | Canonical ingredient or additive name. |
| `entity_type` | yes | `ingredient`, `additive`, or `unknown`. |
| `is_precautionary` | yes | `true` for advisory statements such as “may contain”. |
| `annotation_status` | yes | `reviewed`, `ambiguous`, or `rejected`. |
| `annotator` | yes | Person who reviewed the label. |
| `notes` | no | Reason for an ambiguous or rejected annotation. |

Do not add synthetic variants to the raw file. Augmented samples must retain the original `source_id` and be generated only after the source-aware train/hold-out split.

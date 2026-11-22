# FoodLence dataset format

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

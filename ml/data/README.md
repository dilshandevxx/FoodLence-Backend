# FoodLence ML datasets

## FoodLence V4 pipeline and current authority

The V4 ingredient-classification dataset considered authoritative for the Phase
6A audit is `foodlence_generated_v4/phase4b_corrected/`. It contains a fixed
hybrid dataset and its existing train/validation/test assignment. Phase 6A-R1
adds contributor-level provenance to those rows; it does not generate examples
or change splits. The separate multi-label allergen dataset is under
`foodlence_generated_v4/phase5/` and must never be counted as ingredient
classification data. Consolidated audit files are generated under
`foodlence_generated_v4/final_reports/`.

### V4 phases

1. **Foundation and taxonomy:** `v4/taxonomy.py` defines stable class IDs;
   `v4/validate.py` checks taxonomy structure. The 180 bundled class names
   come from the earlier synthetic vocabulary and are marked unverified.
2. **Source extraction:** `v4/extract_sources.py` extracts ingredient phrases
   from the local Open Food Facts CSV, hashes the source file, records source
   row IDs, and assigns only exact explicit taxonomy matches. These labels are
   provisional.
3. **Controlled synthetic generation and matching analysis:**
   `v4/generate_variants.py` produces explicitly flagged taxonomy-derived
   surface forms; `analyze_foodlence_v4_phase3a.py` and the Phase 3A output
   record unmatched phrases and conservative normalization analysis. Synthetic
   forms are not independent semantic examples or reviewed labels.
4. **Deduplication and splits:** `v4/deduplicate.py` consolidates identical
   phrase/class mappings; `v4/split_dataset.py` groups related semantic forms
   and synthetic parents before deterministic splitting. The hybrid generator
   combines source and synthetic contributors. Missing product IDs prevent a
   product-level independence guarantee.
5. **Separate allergen processing:** `v4/allergens.py` parses multi-label
   source annotations using an explicit exact-match ontology. `dairy` is not
   merged into `milk`, and `tree nuts` is not merged into `nuts`. Empty lists
   mean unknown/unlabeled, never allergen-free. Source labels are not assumed
   human-reviewed.
6. **Provenance enrichment and audit:** `v4/enrich_provenance.py` reconstructs
   each accepted example's contributor-level records from Phase 2 and Phase 3B
   inputs without changing the Phase 4B examples or split assignments.
   `v4/final_reports.py` reconciles the corrected ingredient output and the
   distinct Phase 5 allergen output and writes machine-readable/Markdown
   quality and Task 02 gap reports.

### CLI and regeneration

From the repository root, the supported commands are:

```powershell
python ml/data/build_foodlence_v4.py --help
python ml/data/build_foodlence_v4.py --validate-taxonomy
python ml/data/build_foodlence_v4.py --extract-sources
python ml/data/build_foodlence_v4.py --generate-candidates
python ml/data/build_foodlence_v4.py --prepare-hybrid-splits
python -m ml.data.v4.enrich_provenance
python ml/data/build_foodlence_v4.py --process-allergens
python ml/data/build_foodlence_v4.py --generate-final-reports
```

Generation commands refuse to overwrite existing outputs. For a full
regeneration, preserve the existing artifacts, generate each phase into a new
output directory using `--output-dir` where supported, then run provenance
enrichment and final reporting against the intended corrected directories.
Phase 6A-R2 reporting itself only reads the authoritative corrected ingredient
CSVs and existing Phase 5 allergen outputs; it does not create ingredients,
change splits, or train a model. All generated V4 files are Git-ignored.

### Output and evidence semantics

- `phase4b_corrected/ingredients_all.csv` is one row per accepted normalized
  phrase/class example. Its train, validation, and test files must partition
  these rows exactly once. `ingredients_provenance.csv` is one row per source
  or synthetic contributor and preserves contributor identifiers, references,
  mapping method, validation status, and review status.
- `phase5/allergens_all.csv` contains separate multi-label records with source
  file hashes and row IDs; quarantine and rejection outputs retain problematic
  rows. It is not merged into ingredient-classification examples.
- `final_reports/` contains `v4_quality_report.json/.md`, per-class and split
  coverage CSVs, per-example provenance summary, allergen summary, and Task 02
  gap analysis. Counts are computed from local outputs; CSV SHA-256 values
  identify the files audited.
- **Structural validation** verifies schemas, references, count reconciliation,
  and split constraints. **Independent semantic verification** requires
  authoritative evidence beyond these structural checks. **Human review**
  requires actual annotation/review records. Current source-derived labels are
  provisional exact taxonomy matches; synthetic examples inherit unverified
  taxonomy labels. Neither is represented as independently verified or
  human-reviewed ground truth.
- Current splits are useful for pipeline development only. Related phrase,
  semantic-form, and known parent grouping can be audited, but unavailable
  product IDs mean product-level leakage cannot be ruled out. Class coverage is
  uneven, especially outside training; these splits do not establish real-world
  model performance.

## V4 Phase 6B-1: vocabulary discovery

`python ml/data/discover_foodlence_vocabulary.py --help` describes the separate
discovery CLI. By default it reads Phase 2 `unmatched_candidates.csv` and
writes candidate-only reports to `foodlence_generated_v4/phase6b1/`. It
aggregates repeated normalized phrases while retaining every contributor's
candidate ID, source file hash, source row ID, and source text in the
`source_references` JSON cell. It generates category CSVs, a future human-review
queue, and an occurrence-reconciliation report. The output directory must not
already exist; discovery refuses to overwrite prior results.

Discovery categories and priority scores are deterministic triage heuristics,
not semantic confidence. The tool does not infer mappings from string
similarity, split compound expressions, add taxonomy classes or aliases, or
assign E-number mappings. Every candidate is `unverified` and
`not_human_reviewed`; the human review queue is a list for future review, not a
record of completed review. Non-ASCII phrases are only possible language
variation signals, not language identifications. The authoritative corrected
ingredient dataset and taxonomy are read-only during this phase.

## V4 Phase 6B-2: prioritization and review preparation

Run `python ml/data/prioritize_foodlence_vocabulary.py --help` for the
prioritization CLI. Its default input is the Phase 6B-1 vocabulary inventory;
its default output is `foodlence_generated_v4/phase6b2/`. The default shortlist
limit is 500 and can be changed with `--limit`. Selection uses maximum
allocations of 300 standalone candidates, 150 additive candidates, and 50
investigation candidates (with a separate compound share). Candidates below
the documented score threshold, over-represented ingredient families, and
punctuation/spacing variants are deferred instead of being used to fill slots.
All deferred phrases remain in `deferred_candidates.csv` and their complete
source references remain in the unchanged Phase 6B-1 inventory.

Priority combines capped occurrence frequency, candidate type, exact
candidate-specific documentary evidence, distinction from existing canonical
terms, evidence-backed usefulness for underrepresented classes, and complexity
and ambiguity penalties. The formula and family caps are recorded in
`prioritization_report.json` and `.md`. Scores determine review order only;
they do not measure scientific correctness.

`candidate_evidence_registry.csv` records source occurrence references,
document identifiers, exact URLs and terminology, evidence status, proposed
relationships, and ambiguity notes. Evidence found in an official reference
does not complete human review. `human_review_template.csv` contains concise
source-reference samples, a registry key for the full references, blank reviewer
decision/identity/date/justification fields, and `pending_human_review` status.
Proposed class relationships stay inactive; all candidates remain
`not_integrated`. Compound expressions and selected complex terms appear in a
separate investigation queue and are not automatically decomposed.

The Phase 6B-2 output is a review aid only. It does not modify the taxonomy,
the corrected ingredient dataset, its splits, or the Phase 5 allergen data.
The Phase 6B-2 output directory is Git-ignored with the other generated V4
artifacts.

## FoodLence V4 foundation (Phase 1)

Run `python ml/data/build_foodlence_v4.py --help` for CLI options or
`python ml/data/build_foodlence_v4.py --validate-taxonomy` for deterministic
structural checks. The bundled 180-class taxonomy reuses the names and
categories in the synthetic fresh generator. Its entries are marked
`unverified`: the repository does not contain authoritative taxonomy sources,
completed SQL seed data, verified aliases, or confirmed E-number mappings.
Passing structural validation does not establish scientific or regulatory
correctness. The Phase 1 scope was taxonomy and validation; later V4 phases
provide the separate extraction, synthetic candidate, integration, allergen,
and reporting tools documented above.

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

## V4 Phase 6B-3: vocabulary candidate review

Run `python ml/data/review_foodlence_vocabulary.py --help` to prepare reviewer
batches from the Phase 6B-2 shortlist. The default local output is
`foodlence_generated_v4/phase6b3/`. The workflow preserves source references,
keeps the 452 shortlisted candidates in deterministic batches, and reconciles
the 154 additive proposals as 150 additive-category candidates plus four
evidence-based proposals from other discovery categories.

No review decisions are supplied by default: candidates remain pending and
approval/rejection exports are empty. Imported CSV decisions are claims until
matched by a separate independent attestation from an externally trusted
allowlist. Even attested approvals are not integrated into taxonomy or
training data. See `review_workflow_guide.md` in the generated output before
collecting or importing decisions.

## V4 Phase 6B-4: evidence-enriched review pilot

Run `python ml/data/review_foodlence_pilot.py --help` to prepare the first 50
candidate records from the first Phase 6B-3 manifest batch. Outputs go to
`foodlence_generated_v4/phase6b4/`. Evidence is candidate-specific and records
its limits; a checked reference is not a human decision or an activated class
mapping. The pilot also creates a separate example-level review template from
source-derived rows only. Reviewer-controlled fields remain blank, and neither
template changes taxonomy or training data. See `pilot_reviewer_guide.md`.

## V4 Phase 7A: automatic vocabulary expansion

Run python ml/data/expand_foodlence_vocabulary.py to generate a separate
experimental expansion under ml/data/foodlence_generated_v4/phase7a/. The
process preserves all 180 canonical IDs and uses separate PVA/PVB namespaces
for authority-supported provisional concepts and source-observed provisional
terms. Evidence tiers describe evidence or processing, never human-review
status. Every example remains not_human_reviewed; these files do not replace
phase4b_corrected and are not a ground-truth training dataset. The generator
refuses to overwrite an existing Phase 7A output directory.

## V4 Phase 7B: vocabulary audit and experimental exact-match recognition

Run `python -m ml.data.v4.audit_expanded_vocabulary` to create descriptive
quality and in-sample coverage reports under
`ml/data/foodlence_generated_v4/phase7b/`. The recognizer supports exact
normalized lookup only; it does not use fuzzy matching, establish scientific
identity, infer allergen safety, or provide medical or dietary conclusions.
Example: `python ml/data/recognize_foodlence_ingredients.py --phrase "wheat flour" --json`.
For a batch, use `--input-csv input.csv --column ingredient --json`; use
`--include-provenance` to include source references. Batch output defaults to
`phase7b/recognition_results.json` (or CSV without `--json`). Exact matches to
provisional terms are not verified labels. Coverage over vocabulary/source
phrases is in-sample; without an independent human-reviewed benchmark, accuracy,
precision, recall, and F1 are not established. The prototype is separate from
the allergen pipeline and application backend.

## V4 Phase 8: final handover package

Run `python -m ml.data.v4.package_final_dataset --help` for options and `python -m ml.data.v4.package_final_dataset` to package the audited existing outputs into `foodlence_generated_v4/final_package/`. The command refuses to overwrite a non-empty package. It records file hashes and structural checks; it does not rewrite any source-phase outputs.

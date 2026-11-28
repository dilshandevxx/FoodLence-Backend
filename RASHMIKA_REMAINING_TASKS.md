# Rashmika — Remaining ML Responsibilities

**Status checked:** 27 November 2026  
**Scope:** Rashmika's ML Dataset & Training Lead / AI & Semantic Engine Lead responsibilities from `RASHMIKA_RESPONSIBILITIES.md`.

## Current status

The FoodLence V4 dataset pipeline, final dataset package, and exact-match recognition prototype exist. They do not constitute a trained DistilBERT model or a human-reviewed OCR benchmark. The V4 automatic outputs contain provisional and synthetic labels; the current package reports zero documented human-reviewed examples.

## Remaining tasks

### Task 01 — Collect and OCR packaging samples

- Collect food-packaging photos and run Google ML Kit OCR.
- Populate `ml/data/raw/ocr_samples.csv`, preserving the raw OCR text and required capture metadata.
- **Current state:** The CSV has its header but no data rows.

### Task 02 — Build OCR-noise augmentation

- Create `ml/notebooks/01_data_augmentation.ipynb`.
- Generate 3,000 or more controlled OCR-noisy variants from source text, retaining original-to-variant relationships and labels.
- Keep generated variants out of the independent evaluation set.
- **Current state:** The notebook does not exist. Phase 7A automatic vocabulary examples are not a substitute for OCR-noise augmentation.

### Task 03 — Annotate examples and align class labels

- Populate `ml/data/annotated/ocr_ingredients.csv` with at least 3,000 reviewed ingredient mentions and required annotation metadata.
- Align the 150–200 target labels with Heshan's database slugs using an explicit, reviewed crosswalk from FoodLence `FL-*` IDs to database slugs.
- Record reviewer, decision, and rationale; do not treat automatic acceptance as human review.
- **Current state:** The CSV has its header but no examples. The V4 package has 18,626 automatically accepted examples, but zero documented human-reviewed examples.

### Task 04 — Create leakage-aware training and evaluation splits

- Create train and held-out test partitions following the guide's 80/20 target; add a validation partition if needed for model selection.
- Keep source records and generated variants from the same product/package group together wherever product IDs are available.
- Save the independent evaluation data under `ml/data/test/` and report split counts and class coverage.
- **Current state:** `ml/data/test/` contains only `.gitkeep`. Existing V4 splits are not an independent human-reviewed benchmark.

### Task 05 — Fine-tune DistilBERT

- Create `ml/notebooks/02_distilbert_training.ipynb` using `distilbert-base-uncased` and the reviewed, aligned data.
- Implement the documented tokenization and Hugging Face Trainer setup, selecting the best checkpoint using macro-F1 on validation data.
- **Current state:** The training notebook does not exist, and no trained model is present.

### Task 06 — Evaluate and report model quality

- Create `ml/notebooks/03_model_evaluation.ipynb`.
- Evaluate only on the held-out reviewed set. Report macro-F1, macro-precision, macro-recall, confusion matrix, per-class performance, and recall for major allergen classes.
- Target macro-F1: at least 0.85. Report the actual result if the target is not reached.
- Measure CPU inference latency (target under 50 ms per scan) and end-to-end API latency (target under 3 seconds).
- Create `ml/reports/eval_metrics.json` and `ml/reports/confusion_matrix.png`.
- **Current state:** Existing V4 coverage is in-sample and does not establish classifier accuracy. No trained-model evaluation report exists.

### Task 07 — Export the trained model

- Save model weights, tokenizer, configuration, and label mappings under `ml/models/distilbert_foodlence/`.
- Confirm that the saved artifact can be loaded from the configured local model path.
- **Current state:** `ml/models/distilbert_foodlence/` and its model artifacts are absent. `ml/inference.py` expects a local model directory.

### Task 08 — Connect and verify production inference

- Verify segmentation, precautionary phrase handling, batch prediction, and confidence flags in `ml/inference.py` and `app/nlp/` using the trained model.
- Connect model loading/warm-up to FastAPI startup.
- Implement and wire `/api/v1/analyze`, its router registration, and response schema; connect the `<75%` low-confidence flag to the manual-check warning.
- **Current state:** Inference helper code exists, but the analyze endpoint, API router, and analyze schema are TODOs. `app/main.py` does not currently wire the analyze route or model warm-up.

### Task 09 — Complete the semantic fallback

- Implement `app/knowledge_base/semantic_matcher.py` and define its interaction with low-confidence model predictions and the database slug crosswalk.
- Preserve ambiguous and unresolved results; do not force an uncertain match or present an unknown result as safe.
- **Current state:** `semantic_matcher.py` is a TODO. Database integration also requires an agreed, reviewed label crosswalk.

### Task 10 — Add NLP tests and run final QA

- Implement `tests/test_nlp_pipeline.py` for segmentation boundaries, precautionary statements, model loading, batch classification, confidence warnings, unresolved results, and API integration.
- Run `pytest`, Black, and Ruff before handing off the implementation.
- **Current state:** `tests/test_nlp_pipeline.py` is a TODO. Existing V4 tests cover the dataset pipeline, not the complete trained-model/API path.

## Completion gate

The ML responsibilities are not complete until the reviewed OCR dataset, trained/exported model, independent evaluation report, and working inference API are available. Automatic or provisional V4 labels must remain clearly distinguished from reviewed ground truth.

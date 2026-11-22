"""OCR segmentation and lazy DistilBERT inference helpers."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_MODEL_PATH = Path(os.getenv("FOODLENCE_MODEL_PATH", "ml/models/distilbert_foodlence"))
_TOKENIZER: Any = None
_MODEL: Any = None
PRECAUTION = re.compile(r"\b(?:may\s+contain|traces?\s+of|processed\s+in\s+a\s+facility\s+that\s+also\s+handles?)\b", re.I)
START = re.compile(r"\bingredients?\s*[:\-]", re.I)
STOP = re.compile(r"\b(?:nutrition(?:al)?\s+(?:facts|information)|storage\s+instructions|best\s+before|manufactured\s+by)\b", re.I)

def load_model() -> tuple[Any, Any]:
    global _TOKENIZER, _MODEL
    if _MODEL is not None:
        return _TOKENIZER, _MODEL
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Install transformers and torch to run model inference") from exc
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(f"FoodLence model directory was not found: {_MODEL_PATH}")
    _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_PATH)
    _MODEL = AutoModelForSequenceClassification.from_pretrained(_MODEL_PATH)
    _MODEL.eval()
    return _TOKENIZER, _MODEL

def segment(ocr_text: str) -> list[str]:
    if not isinstance(ocr_text, str) or not ocr_text.strip():
        return []
    match = START.search(ocr_text)
    text = ocr_text[match.end():] if match else ocr_text
    stop = STOP.search(text)
    if stop:
        text = text[:stop.start()]
    text = re.sub(r"[\r\n]+", ", ", text)
    return [part.strip(" .:\t") for part in re.split(r"[,;()]", text) if part.strip(" .:\t")]

def is_precautionary(text: str) -> bool:
    return bool(PRECAUTION.search(text or ""))

def predict_ingredients(ocr_text: str) -> list[dict[str, Any]]:
    segments = segment(ocr_text)
    if not segments:
        return []
    tokenizer, model = load_model()
    import torch
    import torch.nn.functional as functional
    inputs = tokenizer(segments, padding=True, truncation=True, max_length=64, return_tensors="pt")
    with torch.inference_mode():
        probabilities = functional.softmax(model(**inputs).logits, dim=-1)
    confidences, ids = torch.max(probabilities, dim=-1)
    labels = getattr(model.config, "id2label", {})
    return [{"raw_segment": text, "predicted_entity": labels.get(int(index), str(int(index))), "confidence": round(float(confidence), 4), "is_low_confidence": float(confidence) < 0.75, "is_precautionary": is_precautionary(text)} for text, confidence, index in zip(segments, confidences, ids)]

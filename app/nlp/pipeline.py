from __future__ import annotations
from ml.inference import is_precautionary, segment
from .classifier import classify
from .confidence import assess

def analyze(ocr_text: str) -> list[dict]:
    predictions = classify(segment(ocr_text))
    return [{"raw_segment": item["text"], "predicted_entity": item["label"], **assess(item["confidence"]), "is_precautionary": is_precautionary(item["text"])} for item in predictions]


from __future__ import annotations
from typing import Any
from .model_loader import get_model

def classify(segments: list[str]) -> list[dict[str, Any]]:
    if not segments:
        return []
    try:
        import torch
        import torch.nn.functional as functional
    except ImportError as exc:
        raise RuntimeError("Install torch to run DistilBERT classification") from exc
    tokenizer, model = get_model()
    inputs = tokenizer(segments, padding=True, truncation=True, max_length=64, return_tensors="pt")
    with torch.inference_mode():
        probabilities = functional.softmax(model(**inputs).logits, dim=-1)
    values, ids = torch.max(probabilities, dim=-1)
    labels = getattr(model.config, "id2label", {})
    return [{"text": text, "label": labels.get(int(index), str(int(index))), "confidence": float(value)} for text, value, index in zip(segments, values, ids)]


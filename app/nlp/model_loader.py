from __future__ import annotations
from typing import Any
from ml.inference import load_model

_resources: tuple[Any, Any] | None = None

def get_model() -> tuple[Any, Any]:
    global _resources
    if _resources is None:
        _resources = load_model()
    return _resources

def warm_up() -> bool:
    tokenizer, _ = get_model()
    tokenizer(["milk"], return_tensors="pt")
    return True

def reset_model_cache() -> None:
    global _resources
    _resources = None


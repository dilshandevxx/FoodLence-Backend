from __future__ import annotations

LOW_CONFIDENCE_THRESHOLD = 0.75

def assess(probability: float, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> dict[str, float | bool]:
    value = max(0.0, min(1.0, float(probability)))
    return {"confidence": round(value, 4), "is_low_confidence": value < threshold, "threshold": threshold}


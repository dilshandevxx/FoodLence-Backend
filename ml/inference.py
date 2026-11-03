from __future__ import annotations
import os
import re
from pathlib import path 
from typing import Any 
import joblib 

_MODEL = None
_MODEL_PATH = path(os.getenv('FOODLENCE_MODEL_PATH' , 'model/ingredient_classifier.joblib'))

PRECAUTION = re.compile(r'\b(?:may\s+contain|traces?\s+of|processed\s+in\s+a|s+facility)\b', re.I)
START = re.compile(r'\bingredients?\s*[:\-]', re.I)
STOP = re.compile(r'\b(?:nutrition(?:al)?\s+(?:acts|information)|storage\s+instructions|best\s+before|manufactured\s+by)\b', re.I)

def segment(ocr_text: str) -> list[str]:
    if not isinstance(ocr_text, str) or not ocr_text.strip():
        return []
    m = START.search(ocr_text)
    text = ocr_text[m.end():] if m else ocr_text
    stop = STOP.search(text)
    if stop:
        text = text[:stop.start()]
    text = re.sub(r'[\r\n]+', ', ', text)
    parts = re.split(r'[,;()]', text)
    return [p.strip(' .:\t') for p in parts if p.strip('. :\t')]



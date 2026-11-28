"""Deterministic provenance-preserving duplicate consolidation."""
from __future__ import annotations
import re, unicodedata, hashlib
from collections import defaultdict

def key(text: str, punctuation: bool = False) -> str:
    value=unicodedata.normalize("NFKC",str(text or "")).casefold()
    value=re.sub(r"\s+"," ",value).strip()
    if punctuation: value=re.sub(r"[-‐‑–—]+"," ",value); value=re.sub(r"\s+"," ",value).strip()
    return value

def deduplicate(rows: list[dict]) -> dict:
    groups=defaultdict(list)
    for row in rows: groups[key(row.get("normalized_text") or row.get("ingredient_text") or row.get("text",""))].append(row)
    accepted=[]; quarantined=[]; duplicate_groups=0; cross_source=0
    for norm, items in sorted(groups.items()):
        labels={r.get("canonical_class_id","") for r in items}
        if len(labels)>1:
            quarantined.extend(dict(r,quarantine_reason="conflicting labels for normalized phrase") for r in items);continue
        if len(items)>1: duplicate_groups+=1
        if len({r.get("source_type","") for r in items})>1: cross_source+=1
        first=dict(items[0]); first["normalized_text"]=norm
        first["provenance_records"]="|".join(sorted({r.get("candidate_id","") for r in items}))
        first["duplicate_occurrences"]=len(items)
        accepted.append(first)
    return {"accepted":accepted,"quarantined":quarantined,"duplicate_groups":duplicate_groups,"cross_source_overlap_groups":cross_source}

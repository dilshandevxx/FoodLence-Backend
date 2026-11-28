"""Deterministic group split and leakage audit."""
from __future__ import annotations
import hashlib
from collections import Counter, defaultdict

def split_groups(rows: list[dict], seed: int=5104) -> dict:
    groups=defaultdict(list)
    for row in rows:
        group=row.get("semantic_form") or row.get("parent_example_id") or row.get("normalized_text")
        groups[group].append(row)
    assignments={}
    for group in sorted(groups):
        bucket=int(hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()[:12],16)%100
        assignments[group]="train" if bucket<80 else "validation" if bucket<90 else "test"
    split_rows={name:[] for name in ("train","validation","test")}
    for group,items in groups.items():
        for row in items:
            split_rows[assignments[group]].append(dict(row,split=assignments[group],split_group=group))
    norm_splits=defaultdict(set); parent_splits=defaultdict(set)
    for part,items in split_rows.items():
        for r in items:
            norm_splits[r.get("normalized_text","")].add(part)
            parent_splits[r.get("parent_example_id","")].add(part)
    leakage={"normalized_phrase_cross_split":sum(len(v)>1 for v in norm_splits.values()),"parent_cross_split":sum(bool(k) and len(v)>1 for k,v in parent_splits.items()),"group_cross_split":sum(len({assignments[g] for g in [k]})>1 for k in assignments)}
    return {"splits":split_rows,"leakage":leakage,"group_count":len(groups),"split_counts":{k:len(v) for k,v in split_rows.items()},"classes_per_split":{k:len({r.get('canonical_class_id') for r in v}) for k,v in split_rows.items()}}

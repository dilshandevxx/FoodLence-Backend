"""Integrate Phase 2 provisional matches with Phase 3B synthetic candidates."""
from __future__ import annotations
import csv, hashlib
from pathlib import Path
from .taxonomy import TAXONOMY
from .deduplicate import deduplicate
from .split_dataset import split_groups

FIELDS=["candidate_id","ingredient_text","normalized_text","canonical_class_id","canonical_name","source_type","source_dataset","source_reference","source_row_id","source_text","parent_example_id","generation_method","is_synthetic","label_method","validation_method","validation_status","validation_reason","review_status","dataset_version","semantic_form"]

def load_hybrid(phase2: Path, phase3b: Path):
    class_names={x.class_id:x.canonical_name for x in TAXONOMY}; rows=[]
    with (phase2/"matched_candidates.csv").open(encoding="utf-8",newline="") as f:
        for x in csv.DictReader(f):
            cid=x["canonical_class_id"]
            rows.append(dict(candidate_id=x["candidate_id"],ingredient_text=x["ingredient_text"],normalized_text=x["normalized_text"],canonical_class_id=cid,canonical_name=class_names.get(cid,""),source_type="source_derived",source_dataset=x["source_dataset"],source_reference=f"sha256:{x['source_file_hash']}",source_row_id=x["source_row_id"],source_text=x["source_text"],parent_example_id="",generation_method=x["extraction_method"],is_synthetic=False,label_method=x["label_method"],validation_method="provisional_exact_taxonomy_match",validation_status=x["validation_status"],validation_reason=x["validation_reason"],review_status="not_human_reviewed",dataset_version="4.0.0",semantic_form=class_names.get(cid,"")))
    with (phase3b/"accepted_candidates.csv").open(encoding="utf-8",newline="") as f:
        for x in csv.DictReader(f):
            if x.get("validation_status")!="accepted" or x.get("is_synthetic","").lower()!="true": continue
            cid=x["canonical_class_id"]
            if cid not in class_names: continue
            rows.append(dict(candidate_id=x["candidate_id"],ingredient_text=x["ingredient_text"],normalized_text=x["normalized_text"],canonical_class_id=cid,canonical_name=class_names[cid],source_type="synthetic_taxonomy",source_dataset=x["source_dataset"],source_reference=x["source_reference"],source_row_id="",source_text=x["ingredient_text"],parent_example_id=x["parent_example_id"],generation_method=x["generation_method"],is_synthetic=True,label_method=x["label_method"],validation_method=x["validation_method"],validation_status="accepted",validation_reason=x["validation_reason"],review_status="not_human_reviewed",dataset_version=x["dataset_version"],semantic_form=x["semantic_form"]))
    return rows

def run(phase2:Path,phase3b:Path,out:Path,seed=5104):
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    rows=load_hybrid(phase2,phase3b); dedup=deduplicate(rows)
    # Dedup groups by phrase. A cross-origin duplicate gets merged source history.
    merged=dedup["accepted"]
    for row in merged:
        origins={r["source_type"] for r in rows if r["normalized_text"]==row["normalized_text"]}
        row["source_contributions"]="|".join(sorted(origins))
        row["provenance_records"]="|".join(sorted(r["candidate_id"] for r in rows if r["normalized_text"]==row["normalized_text"]))
    split=split_groups(merged,seed)
    out.mkdir(parents=True)
    fields=FIELDS+["source_contributions","provenance_records","duplicate_occurrences","split","split_group"]
    def save(name, data):
        with (out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(data)
    allrows=[r for part in split["splits"].values() for r in part]
    save("ingredients_all.csv",allrows);save("ingredients_provenance.csv",allrows)
    for part in ("train","validation","test"):save(f"ingredients_{part}.csv",split["splits"][part])
    save("ingredients_quarantined.csv",dedup["quarantined"])
    source_count=sum(not x["is_synthetic"] for x in rows); synthetic_count=sum(x["is_synthetic"] for x in rows)
    both=sum("source_derived" in x["source_contributions"] and "synthetic_taxonomy" in x["source_contributions"] for x in allrows)
    report={"source_input_occurrences":source_count,"synthetic_input_occurrences":synthetic_count,"cross_source_overlap_phrases":sum(len({r['source_type'] for r in rows if r['normalized_text']==p})>1 for p in {r['normalized_text'] for r in rows}),"combined_input_occurrences":len(rows),"unique_accepted_hybrid_examples":len(allrows),"source_only_accepted":sum(x['source_contributions']=='source_derived' for x in allrows),"synthetic_only_accepted":sum(x['source_contributions']=='synthetic_taxonomy' for x in allrows),"both_source_accepted":both,"quarantined":len(dedup['quarantined']),"conflicting_label_groups":len(dedup['quarantined'])>0,"class_coverage":len({x['canonical_class_id'] for x in allrows}),"review_status":"not_human_reviewed","source_labels_remain_provisional":True}
    import json
    (out/"hybrid_integration_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (out/"deduplication_report.json").write_text(json.dumps({"input_occurrences":len(rows),"unique_accepted":len(merged),"quarantined":len(dedup['quarantined']),"cross_source_overlap_phrases":report['cross_source_overlap_phrases']},indent=2),encoding="utf-8")
    (out/"split_report.json").write_text(json.dumps({"seed":seed,"counts":split['split_counts'],"classes_per_split":split['classes_per_split']},indent=2),encoding="utf-8")
    (out/"leakage_report.json").write_text(json.dumps(split['leakage'],indent=2),encoding="utf-8")
    (out/"evaluation_limitations.md").write_text("# Evaluation limitations\n\nSource labels are provisional weak matches; synthetic labels inherit an unverified taxonomy. The source lacks product identifiers. Surface variants have limited semantic diversity, distribution shift is possible, and no human-reviewed ground truth exists. These splits do not establish real-world accuracy.\n",encoding="utf-8")
    return report

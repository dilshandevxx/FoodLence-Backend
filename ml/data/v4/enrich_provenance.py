"""Enrich existing Phase 4B examples with complete contributor-level provenance."""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import defaultdict,Counter
from pathlib import Path

def _read(path):
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def _adapt_source(row):
    return {**row,"source_type":"source_derived","canonical_class_id":row.get("canonical_class_id",""),"is_synthetic":False}

def _adapt_synthetic(row):
    return {**row,"source_type":row.get("source_type") or "synthetic_taxonomy","is_synthetic":str(row.get("is_synthetic","")).casefold()=="true"}

def enrich(source_rows,synthetic_rows,accepted_rows,split_rows):
    accepted_keys={(r["normalized_text"],r["canonical_class_id"]):r for r in accepted_rows}
    split_keys={(r["normalized_text"],r["canonical_class_id"]):r["split"] for r in split_rows}
    if len(accepted_keys)!=len(accepted_rows):raise ValueError("accepted rows have duplicate phrase/class keys")
    if set(accepted_keys)!=set(split_keys):raise ValueError("split files do not exactly partition accepted examples")
    contributors=defaultdict(list); unmatched=[]; conflicts=[]
    for raw in source_rows:
        row=_adapt_source(raw); key=(row.get("normalized_text",""),row.get("canonical_class_id",""))
        if key not in accepted_keys:
            phrase_matches=[x for x in accepted_rows if x.get("normalized_text")==key[0]]
            item={"candidate_id":row.get("candidate_id"),"reason":"canonical mismatch" if phrase_matches else "no accepted phrase match"}
            (conflicts if phrase_matches else unmatched).append(item);continue
        contributors[key].append(row)
    for raw in synthetic_rows:
        row=_adapt_synthetic(raw)
        if not row["is_synthetic"]:continue
        key=(row.get("normalized_text",""),row.get("canonical_class_id",""))
        if key not in accepted_keys:
            phrase_matches=[x for x in accepted_rows if x.get("normalized_text")==key[0]]
            item={"candidate_id":row.get("candidate_id"),"reason":"canonical mismatch" if phrase_matches else "no accepted phrase match"}
            (conflicts if phrase_matches else unmatched).append(item);continue
        contributors[key].append(row)
    enriched=[]
    for accepted in accepted_rows:
        key=(accepted["normalized_text"],accepted["canonical_class_id"]); records=contributors[key]
        objects=[]
        for r in records:
            objects.append({k:r.get(k) for k in ("candidate_id","source_type","source_dataset","source_file_hash","source_reference","source_row_id","ingredient_text","source_text","normalized_text","canonical_class_id","label_method","generation_method","is_synthetic","validation_status","validation_reason","review_status")})
        objects.sort(key=lambda x:(str(x.get("candidate_id")),str(x.get("source_row_id"))))
        types={x.get("source_type") for x in objects}
        category="both" if {"source_derived","synthetic_taxonomy"}.issubset(types) else "source_only" if "source_derived" in types else "synthetic_only"
        enriched.append({**accepted,"contributor_provenance":json.dumps(objects,sort_keys=True,separators=(",",":"),ensure_ascii=False),"provenance_category":category})
    return enriched,unmatched,conflicts

def run(base:Path,out:Path):
    if out.exists():raise FileExistsError(f"Refusing to overwrite {out}")
    p2=_read(base/"phase2"/"matched_candidates.csv");p3=_read(base/"phase3b"/"synthetic_candidates.csv");allr=_read(base/"phase4b"/"ingredients_all.csv")
    splits=[]
    for part in ("train","validation","test"):splits.extend(_read(base/"phase4b"/f"ingredients_{part}.csv"))
    enriched,unmatched,conflicts=enrich(p2,p3,allr,splits)
    out.mkdir(parents=True)
    fields=list(allr[0])+["contributor_provenance","provenance_category"]
    by_split={s:[r for r in enriched if r["split"]==s] for s in ("train","validation","test")}
    def write(name,rows,cols=fields):
        with (out/name).open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader();w.writerows(rows)
    write("ingredients_all.csv",enriched)
    for part,rows in by_split.items():write(f"ingredients_{part}.csv",rows)
    provenance_rows=[]
    for example in enriched:
        for obj in json.loads(example["contributor_provenance"]):provenance_rows.append({"accepted_example_id":example["candidate_id"],**obj})
    provfields=["accepted_example_id","candidate_id","source_type","source_dataset","source_file_hash","source_reference","source_row_id","ingredient_text","source_text","normalized_text","canonical_class_id","label_method","generation_method","is_synthetic","validation_status","validation_reason","review_status"]
    write("ingredients_provenance.csv",provenance_rows,provfields)
    write("unmatched_contributors.csv",unmatched,["candidate_id","reason"]);write("conflicting_contributors.csv",conflicts,["candidate_id","reason"])
    categories=Counter(r["provenance_category"] for r in enriched)
    report={"source_contributor_occurrences":len(p2),"synthetic_contributor_occurrences":sum(str(x.get("is_synthetic","")).casefold()=="true" for x in p3),"total_contributor_occurrences":len(provenance_rows),"accepted_examples":len(enriched),"categories":dict(categories),"unmatched_contributors":len(unmatched),"conflicting_contributors":len(conflicts),"split_counts":{s:len(v) for s,v in by_split.items()},"provenance_record_count_matches_inputs":len(provenance_rows)==len(p2)+len(p3),"review_status":"not_human_reviewed","labels_unchanged":True,"splits_unchanged":True}
    (out/"provenance_enrichment_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument("--base",type=Path,default=Path(__file__).parents[1]/"foodlence_generated_v4");p.add_argument("--output",type=Path,default=None);a=p.parse_args();print(json.dumps(run(a.base,a.output or a.base/"phase4b_corrected"),indent=2))
if __name__=="__main__":main()

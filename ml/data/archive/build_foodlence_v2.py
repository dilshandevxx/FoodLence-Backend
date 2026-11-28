#!/usr/bin/env python3
"""Conservative, reproducible FoodLence dataset builder. Python stdlib only."""
import argparse, ast, csv, hashlib, json, random, re
from pathlib import Path
from collections import Counter, defaultdict

SEED=5104
DEFAULT_ROOT=Path(r'E:\Foodlence\FoodLence-Backend\ml\data')
E_PATTERN=re.compile(r'(?i)^E\s*[- ]?\s*(\d{3,4}[a-z]?)$')

def norm(s): return re.sub(r'\s+', ' ', str(s).strip().lower())
def group_key(s): return hashlib.sha256(norm(s).encode()).hexdigest()
def split(key):
    n=int(hashlib.sha256((str(SEED)+key).encode()).hexdigest()[:12],16)%100
    return 'train' if n<80 else ('validation' if n<90 else 'test')
def noise(s, rng):
    ops=[]
    for i,c in enumerate(s):
        if c in 'aeios' : ops.append(s[:i]+{'a':'4','e':'3','i':'1','o':'0','s':'5'}[c]+s[i+1:])
        if i+1<len(s) and s[i].isalpha() and s[i+1].isalpha(): ops.append(s[:i]+s[i+1]+s[i]+s[i+2:])
    ops=[x for x in ops if x!=s]
    return rng.choice(ops) if ops else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    ap.add_argument('--ocr',type=Path,default=Path(r'E:\Foodlence\Food Packaging OCR Dataset'))
    ap.add_argument('--min-classes',type=int,default=150)
    ap.add_argument('--max-classes',type=int,default=200)
    ap.add_argument('--min-rows',type=int,default=3000)
    args=ap.parse_args()
    root=args.root; src=root/'raw'; out=root/'foodlence_generated_v2'; out.mkdir(parents=True,exist_ok=True)
    report={'seed':SEED,'source_files':{},'warnings':[],'method':'Exact ingredient phrase and unambiguous E-number to name mappings; automated, not human verified','licenses':'NOT VERIFIED: review source licenses before sharing or distribution'}
    off=src/'openfoodfacts_filtered.csv'; allergy=src/'allergies_10k.csv'
    if not off.exists(): raise SystemExit(f'Missing {off}')
    report['source_files']['off']=str(off)
    # No product IDs: group by normalized source text. Do not use additive lists as labels for unrelated ingredient phrases.
    observed=defaultdict(set); e_names=defaultdict(set); e_sources=defaultdict(set); raw_count=0; ambiguous=0
    with off.open(encoding='utf-8-sig',newline='',errors='replace') as f:
        rd=csv.DictReader(f)
        for i,r in enumerate(rd,2):
            raw_count+=1
            phrase=norm(r.get('ingredient',''))
            if phrase and len(phrase)<=90 and re.fullmatch(r"[a-z0-9 ,()'./+%-]+",phrase) and not any(x in phrase for x in (';', ':', '\\n')) and phrase.count(',')==0:
                # Observed exact phrases only; retain source row provenance.
                observed[phrase].add(i)
            additives=r.get('additives_en','') or ''
            for item in additives.split(','):
                m=re.match(r'^\s*(E\d{3,4}[a-z]?)\s*-\s*(.+?)\s*$',item,re.I)
                if m:
                    code=norm(m.group(1)).replace(' ',''); name=norm(m.group(2))
                    if 2<=len(name)<=75 and re.fullmatch(r"[a-z0-9 ()'./+-]+",name):
                        e_names[code].add(name); e_sources[code].add(i)
    # Only codes with a single consistent canonical name; do not infer ingredient-to-additive association.
    candidates=[]
    for phrase,ids in observed.items():
        if len(phrase)>=3 and len(phrase.split())<=5 and not re.search(r'\d+\s*%',phrase):
            candidates.append((phrase,phrase,ids,'ingredient_exact'))
    for code,names in e_names.items():
        if len(names)==1:
            name=next(iter(names)); candidates.append((code,name,e_sources[code],'additive_code'))
        else: ambiguous+=1
    # Prefer frequently observed classes, deterministic tie break. Additive code rows remain distinct labels.
    by_label=defaultdict(list)
    for phrase,label,ids,kind in candidates: by_label[label].append((phrase,ids,kind))
    ordered=sorted(by_label,key=lambda l:(-sum(len(ids) for _,ids,_ in by_label[l]),l))
    labels=ordered[:args.max_classes]
    rng=random.Random(SEED); rows=[]
    for label in labels:
        for phrase,ids,kind in by_label[label]:
            # One representative observed source row; duplicate occurrences recorded in report.
            source_row=min(ids); key=group_key(phrase); sp=split(key)
            base={'text':phrase,'label':label,'source_id':f'off-row-{source_row}','source_file':off.name,'source_row':source_row,'source_text':phrase,'source_occurrences':len(ids),'mapping_method':kind,'is_synthetic':False,'split':sp,'license_status':'unverified'}
            rows.append(base)
            for j in range(15):
                variant=noise(phrase,rng)
                if variant and variant!=phrase:
                    rows.append({**base,'text':variant,'is_synthetic':True,'variant_index':j+1})
    # Deduplicate within label/split; drop collisions across labels to avoid contradictory ground truth.
    collisions=defaultdict(set)
    for r in rows: collisions[norm(r['text'])].add(r['label'])
    rows=[r for r in rows if len(collisions[norm(r['text'])])==1]
    unique={}
    for r in rows: unique.setdefault((r['split'],r['label'],r['text']),r)
    rows=list(unique.values())
    fields=['text','label','source_id','source_file','source_row','source_text','source_occurrences','mapping_method','is_synthetic','split','license_status','variant_index']
    for sp in ('train','validation','test'):
        with (out/f'ingredients_{sp}.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(r for r in rows if r['split']==sp)
    report.update(off_source_rows=raw_count,observed_unique_phrases=len(observed),candidate_canonical_classes=len(by_label),selected_classes=len(labels),generated_rows=len(rows),split_sizes=dict(Counter(r['split'] for r in rows)),class_counts=dict(Counter(r['label'] for r in rows)),ambiguous_e_number_names=ambiguous,conflicting_variant_texts=sum(len(v)>1 for v in collisions.values()))
    report['warnings']+=['No source product IDs: splitting by exact normalized phrase only. Product-level independence CANNOT be guaranteed. Do not treat these as leakage-safe benchmark splits.','Ingredient phrase labels are exact-string weak supervision, not manually validated entity mappings.','Synthetic OCR variants are heuristic and not calibrated against real OCR errors.']
    if len(labels)<args.min_classes or len(rows)<args.min_rows: report['warnings'].append('Requested target NOT met; no extra classes or source records fabricated.')
    # Allergy separate dataset; preserve literal list labels and do not infer missing/negative labels.
    if allergy.exists():
        report['source_files']['allergy']=str(allergy); ar=[]; parse_errors=0
        with allergy.open(encoding='utf-8-sig',newline='',errors='replace') as f:
            for i,r in enumerate(csv.DictReader(f),2):
                phrase=(r.get('ingredient') or '').strip(); raw=r.get('allergens','')
                try:
                    labels0=ast.literal_eval(raw)
                    if not isinstance(labels0,list) or not all(isinstance(x,str) for x in labels0): raise ValueError()
                except (ValueError,SyntaxError,TypeError): parse_errors+=1;continue
                if not phrase: continue
                ar.append({'text':phrase,'labels':json.dumps(sorted(set(norm(x) for x in labels0))),'source_id':f'allergy-row-{i}','source_row':i,'source_file':allergy.name,'split':split(group_key(phrase)),'is_synthetic':False,'license_status':'unverified'})
        for sp in ('train','validation','test'):
            with (out/f'allergens_{sp}.csv').open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['text','labels','source_id','source_row','source_file','split','is_synthetic','license_status']);w.writeheader();w.writerows(r for r in ar if r['split']==sp)
        report['allergen_rows']=len(ar);report['allergen_parse_errors']=parse_errors;report['allergen_split_sizes']=dict(Counter(r['split'] for r in ar))
        report['warnings'].append('Allergen labels are inherited from source; negative [] may mean unlabeled rather than confirmed absence.')
    else: report['warnings'].append('Allergen CSV missing.')
    report['ocr_inventory_note']='OCR dataset left untouched. No annotation mapping was supplied; OCR evaluation NOT performed.'
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Wrote',out,'ingredient rows:',len(rows),'classes:',len(labels),'allergen rows:',report.get('allergen_rows',0))
    print('WARNING: Weak labels and no product IDs; not a validated production training dataset.')
if __name__=='__main__': main()

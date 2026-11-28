#!/usr/bin/env python3
"""Conservative, reproducible FoodLence dataset builder. Python 3.9+, stdlib only.
OFF ingredient tags are machine-provided canonical candidates, not human verification.
Rows are generated only when an ingredient name appears as a whole phrase in the
source ingredient text and matches a source ingredient tag for that product.
"""
import argparse,csv,hashlib,json,re,random,collections,datetime,pathlib,os,sys
DEFAULTS={'off':r'E:\SEM V\SE5104 - Mini Project - openfoodfacts','ocr':r'E:\Foodlence\Food Packaging OCR Dataset','allergy':r'E:\SEM V\SE5104 - Mini Project - allergies 10k','out':r'E:\Foodlence\FoodLence-Backend\ml\data\foodlence_generated'}
SEED=5104
ALIASES={'en:milk':'milk','en:milk-powder':'milk powder','en:sugar':'sugar','en:salt':'salt'}
def norm(s):return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',str(s).lower())).strip()
def digest(s):return hashlib.sha256(str(s).encode('utf-8')).hexdigest()
def files(root):
 p=pathlib.Path(root)
 if p.is_file():return [p]
 if not p.exists():return []
 return sorted((x for x in p.rglob('*') if x.is_file()),key=lambda x:str(x).lower())
def csvs(root):return [p for p in files(root) if p.suffix.lower() in ('.csv','.tsv')]
def reader(path):
 with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
  first=f.readline();f.seek(0)
  dialect='\t' if path.suffix.lower()=='.tsv' or first.count('\t')>first.count(',') else ','
  yield from csv.DictReader(f,delimiter=dialect)
def columns(p):
 try:
  with p.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
   line=f.readline()
  return [x.strip().strip('"') for x in line.rstrip('\n\r').split('\t' if p.suffix.lower()=='.tsv' or line.count('\t')>line.count(',') else ',')]
 except Exception:return []
def choose_off(root):
 candidates=[]
 for p in csvs(root):
  cols=set(columns(p));score=sum(x in cols for x in ('ingredients_text','ingredients_tags','code','id','_id'))
  if 'ingredients_text' in cols and 'ingredients_tags' in cols:candidates.append((score,p.stat().st_size,p))
 return sorted(candidates,reverse=True)[0][2] if candidates else None
def source_split(key):
 x=int(digest('split-v1:'+key)[:12],16)%100
 return 'train' if x<80 else 'validation' if x<90 else 'test'
def noise(s,rng):
 if len(s)<4:return None
 opts=[]
 for i,c in enumerate(s):
  if c in 'oieas':opts.append(s[:i]+{'o':'0','i':'1','e':'3','a':'4','s':'5'}[c]+s[i+1:])
  if c.isalpha():opts.append(s[:i]+s[i+1:])
 if len(s)>5:
  for i in range(len(s)-1):
   if s[i].isalpha() and s[i+1].isalpha() and s[i]!=s[i+1]:opts.append(s[:i]+s[i+1]+s[i]+s[i+2:])
 opts=[x for x in opts if x and x!=s]
 return rng.choice(opts) if opts else None
def write_csv(path,rows,cols):
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
def main():
 ap=argparse.ArgumentParser();[ap.add_argument('--'+k,default=v) for k,v in DEFAULTS.items()]
 ap.add_argument('--max-classes',type=int,default=200);ap.add_argument('--min-products-per-class',type=int,default=3)
 ap.add_argument('--max-variants-per-original',type=int,default=3);args=ap.parse_args()
 out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
 report={'method':'conservative OFF tag + whole phrase match; automatic labels, NOT human verified','seed':SEED,'input_locations':{'off':args.off,'ocr':args.ocr,'allergy':args.allergy},'warnings':[],'license':'Unverified: review each source license and attribution requirements before distribution.'}
 off=choose_off(args.off)
 report['open_food_facts_file']=str(off) if off else None
 report['ocr_inventory']={'file_count':len(files(args.ocr)),'extension_counts':dict(collections.Counter(p.suffix.lower() for p in files(args.ocr))),'split_directory_names':sorted(set(p.name for p in pathlib.Path(args.ocr).rglob('*') if p.is_dir() and p.name.lower() in ('train','training','val','valid','validation','test'))) if pathlib.Path(args.ocr).exists() else []}
 report['ocr_note']='Existing OCR splits are untouched; no packaging text is used as ingredient ground truth.'
 report['allergy_csv_files']=[str(p) for p in csvs(args.allergy)]
 if not off:
  report['warnings'].append('No OFF CSV/TSV with both ingredients_text and ingredients_tags found. No training data generated.')
  (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));return
 # Products with duplicate product IDs are consolidated to one source, preventing split leakage.
 seen=set();original=[];counts=collections.Counter();missing=collections.Counter();ambiguous=0;dupes=0;scanned=0
 for idx,row in enumerate(reader(off),1):
  scanned+=1
  sid=str(row.get('code') or row.get('id') or row.get('_id') or '').strip()
  raw=str(row.get('ingredients_text') or '').strip();tags=str(row.get('ingredients_tags') or '').strip()
  if not sid:missing['missing_source_id']+=1;continue
  if sid in seen:dupes+=1;continue
  seen.add(sid)
  if not raw or not tags:missing['missing_ingredients_text_or_tags']+=1;continue
  # Only English tags are considered because source ingredient text language is uncertain.
  if row.get('ingredients_text_en'):raw=str(row['ingredients_text_en'])
  elif row.get('lang') and row['lang'].lower() not in ('en','english'):missing['non_english_or_unverified_language']+=1;continue
  raw_norm=norm(raw)
  candidates=[]
  for tag in tags.split(','):
   tag=tag.strip()
   if not tag.startswith('en:'):continue
   name=ALIASES.get(tag,tag[3:].replace('-',' '));canonical=norm(name)
   if len(canonical)<3 or canonical.isdigit():continue
   # Exact word-boundary match; never infer from unrelated packaging text.
   if re.search(r'(?<!\w)'+re.escape(canonical)+r'(?!\w)',raw_norm):candidates.append((canonical,tag))
  # A phrase may map to multiple tag identities. Drop those uncertain mappings.
  by_name=collections.defaultdict(set)
  for name,tag in candidates:by_name[name].add(tag)
  for name,ts in by_name.items():
   if len(ts)>1:ambiguous+=1;continue
   tag=next(iter(ts));original.append({'text':name,'label':name,'source_id':sid,'is_synthetic':'false','split':source_split(sid),'source_file':str(off),'source_tag':tag,'original_ingredients_text':raw,'label_method':'automatic_exact_phrase_plus_OFF_tag','source_license':'unverified'})
   counts[name]+=1
 report.update({'products_scanned':scanned,'unique_source_ids':len(seen),'duplicate_source_ids_skipped':dupes,'missing':dict(missing),'ambiguous_phrase_mappings_skipped':ambiguous,'matched_original_phrase_rows_before_class_filter':len(original),'candidate_class_count':len(counts)})
 # Prefer classes with strong product evidence. No padding to reach targets.
 classes=[k for k,v in sorted(counts.items(),key=lambda z:(-z[1],z[0])) if v>=args.min_products_per_class][:args.max_classes]
 allowed=set(classes);selected=[r for r in original if r['label'] in allowed]
 rng=random.Random(SEED);allrows=list(selected);existing={(r['text'],r['label'],r['source_id']) for r in selected}
 for r in selected:
  for _ in range(args.max_variants_per_original):
   variant=noise(r['text'],rng)
   if not variant or (variant,r['label'],r['source_id']) in existing:continue
   existing.add((variant,r['label'],r['source_id']))
   x=dict(r);x['text']=variant;x['is_synthetic']='true';x['label_method']='synthetic_ocr_noise_from_automatic_mapping';allrows.append(x)
 cols=['text','label','source_id','is_synthetic','split','source_file','source_tag','original_ingredients_text','label_method','source_license']
 for split in ('train','validation','test'):write_csv(out/('ingredients_'+split+'.csv'),[r for r in allrows if r['split']==split],cols)
 write_csv(out/'ingredient_class_manifest.csv',[{'label':k,'original_source_phrase_rows':counts[k]} for k in classes],['label','original_source_phrase_rows'])
 report['ingredient_dataset']={'classes':len(classes),'original_rows':len(selected),'synthetic_rows':len(allrows)-len(selected),'total_rows':len(allrows),'split_rows':dict(collections.Counter(r['split'] for r in allrows)),'split_unique_source_ids':{s:len(set(r['source_id'] for r in allrows if r['split']==s)) for s in ('train','validation','test')},'per_class_original_counts':{k:counts[k] for k in classes},'target_3000_rows_met':len(allrows)>=3000,'target_150_to_200_classes_met':150<=len(classes)<=200}
 # Allergen source: inventory only until actual label schema can be confirmed.
 report['allergen_dataset']={'status':'not_generated_unverified_schema','reason':'A multi-label mapping including reliable zero-label examples cannot be inferred from filenames. Review columns and label semantics first.','csv_schemas':{str(p):columns(p) for p in csvs(args.allergy)}}
 report['warnings']+=['Ingredient labels are machine-derived and not human verified.','Exact normalized phrase matches may still be semantically ambiguous; review samples before model use.','OFF license and OCR dataset license have not been independently verified.','OCR dataset was inventoried only; existing train/validation/test partitions were not modified.']
 (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'README.txt').write_text('Generated by build_foodlence.py. Original datasets were not modified. See report.json for limitations and provenance.\n',encoding='utf-8')
 print('Completed. Report:',out/'report.json');print('Classes:',len(classes),'Rows:',len(allrows));print('Allergen dataset requires schema validation; not fabricated.')
if __name__=='__main__':main()

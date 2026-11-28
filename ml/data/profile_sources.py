import csv, json, collections, pathlib, argparse
p=argparse.ArgumentParser();p.add_argument('--root',default=r'E:\Foodlence\FoodLence-Backend\ml\data\raw');a=p.parse_args()
root=pathlib.Path(a.root); report={}
for name in ('openfoodfacts_filtered.csv','allergies_10k.csv'):
 f=root/name
 if not f.is_file(): report[name]={'error':'file not found'};continue
 with f.open(encoding='utf-8-sig',newline='',errors='replace') as stream:
  reader=csv.DictReader(stream); fields=reader.fieldnames or []
  count=0; blanks=collections.Counter(); distinct={k:set() for k in fields}; samples=[]; max_unique=100000
  for row in reader:
   count+=1
   if len(samples)<4: samples.append({k:(v or '')[:180] for k,v in row.items() if k in ('ingredient','allergens','e_numbers','additives','additives_en','')})
   for k in fields:
    v=(row.get(k) or '').strip()
    if not v: blanks[k]+=1
    elif len(distinct[k])<max_unique: distinct[k].add(v)
  report[name]={'rows':count,'columns':fields,'missing':dict(blanks),'unique_upper_bounded':{k:len(v) for k,v in distinct.items()},'unique_count_capped_at':max_unique,'examples':samples}
out=root.parent/'foodlence_source_profile.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('Wrote',out)

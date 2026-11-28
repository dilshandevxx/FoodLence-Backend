#!/usr/bin/env python3
"""Read-only FoodLence source inventory. Python standard library only.
Run from repository root: python ml/data/inspect_foodlence.py --root ml/data
Does not modify source datasets or infer canonical labels.
"""
import argparse, csv, hashlib, json, os, collections
from pathlib import Path

KEYS = ('ingredient','additive','allerg','ocr','packag','openfood','open_food','off','license','licence','readme','metadata')

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def inspect_csv(path, sample_limit=2000):
    result={'columns':[], 'sample_rows':0,'empty_by_column':{},'unique_sample_by_column':{},'likely_id_columns':[], 'likely_text_columns':[], 'error':None}
    try:
        with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
            sample=f.read(16384);f.seek(0)
            try: dialect=csv.Sniffer().sniff(sample,delimiters=',;\t|')
            except csv.Error: dialect=csv.excel
            reader=csv.DictReader(f,dialect=dialect)
            cols=reader.fieldnames or []
            result['columns']=cols
            result['likely_id_columns']=[c for c in cols if any(x in c.lower() for x in ('id','code','barcode','product'))]
            result['likely_text_columns']=[c for c in cols if any(x in c.lower() for x in ('ingredient','additive','text','allergen','label','ocr'))]
            empties=collections.Counter(); unique={c:set() for c in cols}
            for i,row in enumerate(reader):
                if i>=sample_limit:break
                for c in cols:
                    v=(row.get(c) or '').strip()
                    if not v:empties[c]+=1
                    if len(unique[c])<sample_limit:unique[c].add(v)
                result['sample_rows']+=1
            result['empty_by_column']=dict(empties)
            result['unique_sample_by_column']={c:len(s) for c,s in unique.items()}
    except Exception as e:result['error']=str(e)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='ml/data');ap.add_argument('--out',default=None);ap.add_argument('--sample-limit',type=int,default=2000);ap.add_argument('--hash-max-mb',type=int,default=128)
    args=ap.parse_args();root=Path(args.root).resolve()
    if not root.is_dir():raise SystemExit(f'Not found: {root}')
    out=Path(args.out).resolve() if args.out else root/'foodlence_inspection.json'
    entries=[]; dirs=[]
    for folder,subdirs,files in os.walk(root):
        subdirs[:]=sorted(d for d in subdirs if d not in {'.git','__pycache__','.venv','venv'})
        rel=Path(folder).relative_to(root)
        dirs.append(str(rel))
        for name in sorted(files):
            p=Path(folder)/name
            if p.resolve()==out:continue
            st=p.stat(); relp=str(p.relative_to(root)); low=relp.lower()
            entry={'path':relp,'size_bytes':st.st_size,'extension':p.suffix.lower(),'likely_relevant':any(k in low for k in KEYS),'sha256':sha256(p) if st.st_size<=args.hash_max_mb*1024*1024 else None}
            if p.suffix.lower() in ('.csv','.tsv'):
                entry['csv']=inspect_csv(p,args.sample_limit)
            entries.append(entry)
    report={'root':str(root),'read_only':True,'warning':'CSV counts are samples, not full source row counts. No canonical mapping or license verification performed.','directories':dirs,'files':entries,'total_files':len(entries),'csv_files':sum(x['extension'] in ('.csv','.tsv') for x in entries)}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Inspection written:',out)
    print('Files:',report['total_files'],'CSV/TSV:',report['csv_files'])
    for e in entries:
        if e['likely_relevant'] or e['extension'] in ('.csv','.tsv'):
            print(e['path'],f"({e['size_bytes']:,} bytes)")
            if 'csv' in e:print('  columns:',e['csv']['columns'])
    print('No source data was changed.')
if __name__=='__main__':main()

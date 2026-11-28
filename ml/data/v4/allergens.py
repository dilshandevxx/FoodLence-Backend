"""Separate conservative multi-label allergen dataset processing."""
from __future__ import annotations
import ast,csv,hashlib,json,re,unicodedata
from collections import Counter,defaultdict
from pathlib import Path

DATASET_VERSION="5.0.0"
# Source vocabulary is preserved. '**' is a documented source marker, stripped
# exactly; dairy/milk and nuts/tree nuts are deliberately not merged.
DEFAULT_ONTOLOGY={"dairy":"dairy","tree nuts":"tree nuts","celery":"celery","eggs":"eggs","soybeans":"soybeans","wheat":"wheat","gluten":"gluten","sesame":"sesame","sulphur dioxide":"sulphur dioxide","sulphites":"sulphites","fish":"fish","mustard":"mustard","peanuts":"peanuts","lactose":"lactose","shellfish":"shellfish","mollusks":"mollusks"}

def normalize_text(value):
    return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",str(value or "")).strip().casefold())

def parse_labels(raw):
    value=ast.literal_eval(raw)
    if not isinstance(value,list) or not all(isinstance(x,str) for x in value): raise ValueError("expected list of strings")
    return value

def normalize_labels(labels, ontology=None):
    ontology=DEFAULT_ONTOLOGY if ontology is None else ontology
    normalized=[]; unknown=[]
    for label in labels:
        key=normalize_text(label)
        # Only documented source decoration is removed; no semantic merging.
        if key.startswith("**"): key=key[2:].strip()
        mapped=ontology.get(key)
        if mapped is None: unknown.append(label)
        else: normalized.append(mapped)
    return sorted(set(normalized)),unknown

def process_allergens(input_path:Path,output_dir:Path,ontology=None):
    if output_dir.exists(): raise FileExistsError(f"Refusing to overwrite {output_dir}")
    h=hashlib.sha256()
    with input_path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    source_hash=h.hexdigest(); occurrences=defaultdict(list); rejected=[]; quarantined=[]; empty=0; parse_errors=0; total=0; unknown_counts=Counter()
    with input_path.open(encoding='utf-8-sig',errors='replace',newline='') as f:
        reader=csv.DictReader(f)
        if not {'ingredient','allergens'}.issubset(reader.fieldnames or []): raise ValueError("required columns ingredient/allergens missing")
        for rownum,row in enumerate(reader,2):
            total+=1; original=row.get('ingredient') or ''; text=normalize_text(original)
            if not text:
                rejected.append({'source_row_id':str(rownum),'source_text':original,'reason':'missing ingredient text'});continue
            try: labels=parse_labels(row.get('allergens') or '')
            except (ValueError,SyntaxError,TypeError) as exc:
                parse_errors+=1;rejected.append({'source_row_id':str(rownum),'source_text':original,'reason':f'invalid allergen list: {exc}'});continue
            if not labels: empty+=1
            norm,unknown=normalize_labels(labels,ontology)
            unknown_counts.update(unknown)
            if unknown:
                quarantined.append({'source_row_id':str(rownum),'source_text':original,'original_labels':json.dumps(labels),'reason':'unknown allergen label(s): '+', '.join(sorted(set(unknown)))});continue
            eid=hashlib.sha256(f'{source_hash}:{rownum}:{text}'.encode()).hexdigest()[:24]
            occurrences[text].append({'example_id':eid,'ingredient_text':original,'normalized_ingredient_text':text,'original_allergen_labels':json.dumps(labels,ensure_ascii=False),'normalized_allergen_labels':json.dumps(norm,ensure_ascii=False),'source_dataset':input_path.name,'source_row_id':str(rownum),'source_file_hash':source_hash,'label_method':'source_labels_exact_with_documented_marker_cleanup','validation_status':'accepted_unreviewed' if norm else 'accepted_unlabeled_unknown','validation_reason':'source labels parsed; empty list is unknown, not allergen-free' if not norm else 'labels normalized only by explicit ontology entries','review_status':'not_human_reviewed','dataset_version':DATASET_VERSION})
    accepted=[]; dup_groups=0; conflicts=0
    for text,items in sorted(occurrences.items()):
        labelsets={x['normalized_allergen_labels'] for x in items}
        if len(labelsets)>1:
            conflicts+=1
            for x in items: quarantined.append({'source_row_id':x['source_row_id'],'source_text':x['ingredient_text'],'original_labels':x['original_allergen_labels'],'reason':'duplicate normalized text has conflicting label sets'})
            continue
        if len(items)>1:dup_groups+=1
        row=dict(items[0]);row['provenance_records']=json.dumps([{k:x[k] for k in ('example_id','source_row_id','source_file_hash')} for x in items],ensure_ascii=False);row['duplicate_occurrences']=len(items);accepted.append(row)
    output_dir.mkdir(parents=True)
    fields=list(accepted[0]) if accepted else ['example_id','ingredient_text','normalized_ingredient_text','original_allergen_labels','normalized_allergen_labels','source_dataset','source_row_id','source_file_hash','label_method','validation_status','validation_reason','review_status','dataset_version','provenance_records','duplicate_occurrences']
    def write(name,rows,cols=None):
        with (output_dir/name).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=cols or fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    write('allergens_all.csv',accepted);write('allergens_quarantined.csv',quarantined,['source_row_id','source_text','original_labels','reason']);write('allergens_rejected.csv',rejected,['source_row_id','source_text','reason'])
    counts=Counter(label for r in accepted for label in json.loads(r['normalized_allergen_labels']))
    write('allergen_label_distribution.csv',[{'label':k,'count':v} for k,v in sorted(counts.items())],['label','count'])
    report={'source_rows_processed':total,'accepted_unique_examples':len(accepted),'accepted_occurrences':sum(x['duplicate_occurrences'] for x in accepted),'quarantined':len(quarantined),'rejected':len(rejected),'parse_errors':parse_errors,'empty_label_rows_unknown':empty,'distinct_normalized_labels':len(counts),'label_distribution':dict(counts),'unknown_label_distribution':dict(unknown_counts),'duplicate_groups_merged':dup_groups,'conflicting_duplicate_groups':conflicts,'source_file_hash':source_hash,'review_status':'not_human_reviewed','ontology_scope':'Exact source labels; strips only leading ** marker. Dairy/milk, tree nuts/nuts, and other concepts are not merged.','empty_list_semantics':'unknown or unlabeled; never interpreted as allergen-free'}
    (output_dir/'allergen_quality_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output_dir/'allergen_quality_report.md').write_text('# Allergen dataset quality report\n\n'+'\n'.join(f'- **{k}:** {v}' for k,v in report.items()),encoding='utf-8')
    return report

import csv,json
from ml.data.v4.allergens import parse_labels,normalize_labels,process_allergens

def test_parse_multilabel_empty_and_invalid():
    assert parse_labels("['milk', 'wheat']")==['milk','wheat']
    assert parse_labels('[]')==[]
    try: parse_labels("not a list")
    except (ValueError,SyntaxError): pass
    else: assert False

def test_ontology_is_exact_and_does_not_merge_related_terms():
    labels,unknown=normalize_labels(['**dairy','milk','tree nuts','nuts'])
    assert labels==['dairy','tree nuts'] and unknown==['milk','nuts']

def test_processing_provenance_duplicates_conflicts_empty(tmp_path):
    src=tmp_path/'a.csv'
    with src.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['ingredient','allergens']);w.writeheader()
        w.writerows([{'ingredient':'Almond','allergens':"['tree nuts','**dairy']"},{'ingredient':' almond ','allergens':"['tree nuts','dairy']"},{'ingredient':'plain rice','allergens':'[]'},{'ingredient':'unknown','allergens':"['mystery']"},{'ingredient':'bad','allergens':'x'}])
    out=tmp_path/'out';a=process_allergens(src,out);b=process_allergens(src,tmp_path/'out2')
    assert a==b and a['accepted_unique_examples']==2 and a['duplicate_groups_merged']==1
    rows=list(csv.DictReader((out/'allergens_all.csv').open(encoding='utf-8',newline='')))
    assert all(x['review_status']=='not_human_reviewed' for x in rows)
    assert any(json.loads(x['normalized_allergen_labels'])==[] and x['validation_status']=='accepted_unlabeled_unknown' for x in rows)
    assert a['quarantined']==1 and a['rejected']==1

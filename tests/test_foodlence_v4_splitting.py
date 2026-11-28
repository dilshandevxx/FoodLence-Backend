from ml.data.v4.deduplicate import deduplicate
from ml.data.v4.split_dataset import split_groups

def row(cid="A", text="milk", source="src", parent="p", semantic="milk"):
    return {"candidate_id":text+cid+source,"ingredient_text":text,"normalized_text":text,"canonical_class_id":cid,"source_type":source,"parent_example_id":parent,"semantic_form":semantic}

def test_dedup_merges_provenance_and_quarantines_conflict():
    result=deduplicate([row(),row(source="synthetic"),row(cid="B")])
    assert len(result["accepted"])==0
    assert len(result["quarantined"])==3

def test_split_is_deterministic_and_groups_parent_semantic():
    rows=[row(text="milk"),row(text="m!lk",parent="p",semantic="milk")]
    a=split_groups(rows); b=split_groups(rows)
    assert a["split_counts"]==b["split_counts"]
    assert a["leakage"]["parent_cross_split"]==0
    assert len({r["split"] for part in a["splits"].values() for r in part})==1

def test_empty_input():
    result=split_groups([])
    assert result["split_counts"]=={"train":0,"validation":0,"test":0}

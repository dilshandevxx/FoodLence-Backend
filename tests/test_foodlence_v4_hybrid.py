from pathlib import Path
from ml.data.v4.hybrid import load_hybrid
from ml.data.v4.deduplicate import deduplicate
from ml.data.v4.split_dataset import split_groups

def test_real_phase_inputs_load_and_preserve_status():
    root=Path(__file__).parents[1]/"ml/data/foodlence_generated_v4"
    rows=load_hybrid(root/"phase2",root/"phase3b")
    assert sum(not r["is_synthetic"] for r in rows)==179
    assert sum(r["is_synthetic"] for r in rows)==644
    assert all(r["review_status"]=="not_human_reviewed" for r in rows)
    assert all(r["validation_status"]=="matched_provisional" for r in rows if not r["is_synthetic"])

def test_overlap_merges_provenance_and_split_groups():
    a={"candidate_id":"a","normalized_text":"milk","canonical_class_id":"C","source_type":"source_derived","parent_example_id":"","semantic_form":"milk"}
    b={"candidate_id":"b","normalized_text":"milk","canonical_class_id":"C","source_type":"synthetic_taxonomy","parent_example_id":"p","semantic_form":"milk"}
    result=deduplicate([a,b]); assert result["accepted"][0]["provenance_records"]=="a|b"
    split=split_groups(result["accepted"]); assert split["leakage"]["normalized_phrase_cross_split"]==0

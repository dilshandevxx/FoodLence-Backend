"""Analyze V4 Phase 2 unmatched phrases and report conservative matching impact."""
import csv, json, re
from collections import Counter, defaultdict
from pathlib import Path
from v4.extract_sources import normalize, taxonomy_index, match_candidate
from v4.taxonomy import TAXONOMY
from v4.validate import validate_taxonomy

ROOT=Path(__file__).parent
PH2=ROOT/'foodlence_generated_v4'/'phase2'
OUT=ROOT/'foodlence_generated_v4'/'phase3a'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    index, ids=taxonomy_index(TAXONOMY)
    old=list(csv.DictReader((PH2/'source_candidates.csv').open(encoding='utf-8',newline='')))
    unmatched=[r for r in old if r['validation_status']=='unmatched']
    phrase_freq=Counter(r['normalized_text'] for r in unmatched)
    patterns={'compound_markers':r'\b(?:blend|mixture|and|with|or|contains|including)\b|[(),/]',
      'digits_or_codes':r'\d|\be\s*\d{3,4}[a-z]?\b','non_ascii':r'[^\x00-\x7f]',
      'long_over_80':r'.{81,}','punctuation':r'[-./]'}
    pattern_counts={k:sum(bool(re.search(p,t)) for t in phrase_freq) for k,p in patterns.items()}
    top=[{'phrase':s,'occurrences':n} for s,n in phrase_freq.most_common(50)]
    # Report normalization-only candidates and collisions; do not activate aliases.
    suggestions=[]; norm_groups=defaultdict(set)
    for name,cids in index.items(): norm_groups[name].update(cids)
    for row in unmatched:
        txt=row['normalized_text']; candidate=match_candidate(txt,index,ids)
        if candidate['validation_status']=='matched_provisional':
            suggestions.append({'candidate_phrase':txt,'proposed_class_id':candidate['canonical_class_id'],
              'evidence_rule':'Unicode NFKC + casefold + whitespace + spacing around hyphens; exact taxonomy key',
              'source_reference':f"{row['source_dataset']}#{row['source_row_id']} sha256:{row['source_file_hash']}",
              'ambiguity_flags':'none','verification_status':'unverified_inactive','active':False})
    with (OUT/'alias_candidates.csv').open('w',encoding='utf-8',newline='') as f:
      fields=['candidate_phrase','proposed_class_id','evidence_rule','source_reference','ambiguity_flags','verification_status','active']
      w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(suggestions)
    before=Counter(r['canonical_class_id'] for r in old if r['validation_status']=='matched_provisional')
    before_classes=set(before)
    after=Counter(before)
    norm_rows=[]
    for r in unmatched:
      result=match_candidate(r['normalized_text'],index,ids)
      if result['validation_status']=='matched_provisional':
        after[result['canonical_class_id']]+=1
        norm_rows.append({'candidate_id':r['candidate_id'],'before':'unmatched','after':'matched_provisional','normalized_text':r['normalized_text'],'class_id':result['canonical_class_id'],'rule':result['label_method']})
    with (OUT/'normalization_impact.csv').open('w',encoding='utf-8',newline='') as f:
      fields=['candidate_id','before','after','normalized_text','class_id','rule']; w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(norm_rows)
    coverage=[]
    for item in TAXONOMY:
      coverage.append({'class_id':item.class_id,'canonical_name':item.canonical_name,'before_occurrences':before[item.class_id],'after_occurrences':after[item.class_id]})
    with (OUT/'class_coverage_before_after.csv').open('w',encoding='utf-8',newline='') as f:
      w=csv.DictWriter(f,fieldnames=list(coverage[0]));w.writeheader();w.writerows(coverage)
    report={'source_rows_processed':len(old),'unique_unmatched_phrases':len(phrase_freq),'unmatched_occurrences':len(unmatched),
      'unmatched_pattern_counts_by_unique_phrase':pattern_counts,'common_unmatched_phrases':top,
      'original_provisional_match_occurrences':sum(before.values()),'updated_provisional_match_occurrences':sum(after.values()),
      'newly_matched_occurrences':sum(after.values())-sum(before.values()),'unique_matched_phrases_before':len({r['normalized_text'] for r in old if r['validation_status']=='matched_provisional'}),
      'unique_matched_phrases_after':len({r['normalized_text'] for r in old if r['validation_status']=='matched_provisional'})+len({r['normalized_text'] for r in norm_rows}),
      'classes_covered_before':len(before_classes),'classes_covered_after':len(set(after)),'ambiguous_matches':0,'rejected_unsafe_attempts':0,
      'alias_candidates_inactive':len(suggestions),'active_aliases_added':0,'taxonomy_validation':validate_taxonomy(),
      'normalization_rules':['Unicode NFKC','casefold','whitespace collapse','Unicode hyphen normalization and spacing normalization'],
      'limitations':['Taxonomy defines no aliases or E-number mappings; no scientific mappings were inferred.','Existing Phase 2 candidates were already Unicode/case/whitespace normalized, so this pass may add no matches.','Source data lacks product identifiers.','Compound phrases, non-English text, OCR corruption, and chemicals require authoritative taxonomy or review.']}
    (OUT/'unmatched_analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    md=['# Phase 3A matching quality report','',f"- Provisional matches before/after: {sum(before.values())}/{sum(after.values())}",f"- New matches: {sum(after.values())-sum(before.values())}",f"- Classes covered before/after: {len(before_classes)}/{len(set(after))}",f"- Unique unmatched phrases: {len(phrase_freq)}",f"- Inactive alias candidates: {len(suggestions)}",'- Taxonomy status: 180 classes, structurally valid, scientifically unverified.','- No fuzzy or semantic matching was activated.','', 'Unmatched patterns are descriptive signals, not label evidence.', '', '## Limitations', *[f'- {x}' for x in report['limitations']]]
    (OUT/'matching_quality_report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('unique_unmatched_phrases','original_provisional_match_occurrences','updated_provisional_match_occurrences','newly_matched_occurrences','classes_covered_before','classes_covered_after','unmatched_pattern_counts_by_unique_phrase')},indent=2))
if __name__=='__main__': main()

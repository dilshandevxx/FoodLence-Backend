#!/usr/bin/env python3
"""FoodLence V3: reproducible weak-label dataset builder (Python standard library).

Run: python ml/data/build_foodlence_v3.py
Source files are read-only. Outputs are experimental, NOT human-verified ground truth.
"""
import argparse
import ast
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

SEED = 5104
DEFAULT_ROOT = Path(r'E:\Foodlence\FoodLence-Backend\ml\data')
E_ITEM = re.compile(r'^\s*(E\s*\d{3,4}[a-z]?)\s*-\s*(.*?)\s*$', re.I)
SAFE_PHRASE = re.compile(r"[a-z0-9 ()'./+%-]+\Z")
FIELDS = ['text','label','source_id','source_file','source_row','source_text',
          'source_occurrences','mapping_method','is_synthetic','split','license_status',
          'variant_index','source_group']


def normalize(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def choose_split(key):
    n = int(digest(f'{SEED}|{key}')[:12], 16) % 100
    return 'train' if n < 80 else ('validation' if n < 90 else 'test')


def acceptable_phrase(s):
    return (3 <= len(s) <= 75 and len(s.split()) <= 5 and
            SAFE_PHRASE.fullmatch(s) is not None and ',' not in s and
            ':' not in s and not re.search(r'\d+\s*%', s))


def variants(text):
    """Deterministic, unique, modest noise; train only. NOT real OCR calibration."""
    out = set()
    confusable = {'a':'4','e':'3','i':'1','o':'0','s':'5','l':'1','b':'8'}
    for i, ch in enumerate(text):
        if ch in confusable:
            out.add(text[:i] + confusable[ch] + text[i+1:])
        if i + 1 < len(text) and text[i].isalpha() and text[i+1].isalpha() and text[i] != text[i+1]:
            out.add(text[:i] + text[i+1] + text[i] + text[i+2:])
        if i + 1 < len(text) and text[i].isalpha() and text[i+1].isalpha():
            out.add(text[:i] + text[i+1:])
    if ' ' in text:
        out.add(text.replace(' ', '', 1))
        out.add(text.replace(' ', '  ', 1))
    return sorted(x for x in out if x and x != text)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def build(args):
    root = args.root
    off = root / 'raw' / 'openfoodfacts_filtered.csv'
    allergy = root / 'raw' / 'allergies_10k.csv'
    if not off.is_file():
        raise SystemExit(f'Missing input CSV: {off}')
    if not allergy.is_file():
        raise SystemExit(f'Missing input CSV: {allergy}')
    out = root / 'foodlence_generated_v3'
    if out.exists() and not args.overwrite:
        raise SystemExit(f'Output already exists: {out}. Use --overwrite to replace V3 outputs only.')
    observed = defaultdict(set)
    e_names = defaultdict(set)
    e_sources = defaultdict(set)
    raw_count = 0
    with off.open(encoding='utf-8-sig', errors='replace', newline='') as f:
        rd = csv.DictReader(f)
        required = {'ingredient', 'additives_en'}
        if not required.issubset(rd.fieldnames or []):
            raise SystemExit(f'Open Food Facts missing columns: {required - set(rd.fieldnames or [])}')
        for rownum, r in enumerate(rd, 2):
            raw_count += 1
            phrase = normalize(r.get('ingredient'))
            if acceptable_phrase(phrase):
                observed[phrase].add(rownum)
            for item in (r.get('additives_en') or '').split(','):
                m = E_ITEM.match(item)
                if not m:
                    continue
                code = normalize(m.group(1)).replace(' ', '')
                name = normalize(m.group(2))
                if acceptable_phrase(name):
                    e_names[code].add(name)
                    e_sources[code].add(rownum)

    # Exact text -> itself is weak supervision, not semantic entity normalization.
    # Code -> name mapping is accepted only if unique within this CSV.
    candidates = [(phrase, phrase, ids, 'ingredient_exact') for phrase, ids in observed.items()]
    ambiguous_codes = {code: sorted(names) for code, names in e_names.items() if len(names) > 1}
    for code, names in e_names.items():
        if len(names) == 1:
            candidates.append((code, next(iter(names)), e_sources[code], 'additive_code'))
    by_label = defaultdict(list)
    for phrase, label, ids, method in candidates:
        by_label[label].append((phrase, ids, method))

    # Rank by observed source occurrences, not synthetic count.
    ordered = sorted(by_label, key=lambda label: (-sum(len(ids) for _, ids, _ in by_label[label]), label))
    selected = ordered[:args.max_classes]
    original = []
    for label in selected:
        for phrase, ids, method in by_label[label]:
            # A source product identifier is not present. A text hash is only a proxy.
            group = digest(normalize(phrase))
            original.append(dict(text=phrase, label=label,
                                 source_id=f'off-row-{min(ids)}', source_file=off.name,
                                 source_row=min(ids), source_text=phrase,
                                 source_occurrences=len(ids), mapping_method=method,
                                 is_synthetic=False, split=choose_split(group),
                                 license_status='unverified', variant_index='', source_group=group))

    # Exclude observed texts with conflicting labels before creating any variants.
    original_labels = defaultdict(set)
    for r in original:
        original_labels[normalize(r['text'])].add(r['label'])
    conflicts = {t for t, labs in original_labels.items() if len(labs) > 1}
    original = [r for r in original if normalize(r['text']) not in conflicts]

    # Only training examples are augmented. A global text->label guard prevents
    # collisions against original validation/test texts and other class variants.
    reserved = defaultdict(set)
    for r in original:
        reserved[normalize(r['text'])].add(r['label'])
    synthetic = []
    collision_skips = 0
    for base in sorted(original, key=lambda r: (r['label'], r['text'])):
        if base['split'] != 'train':
            continue
        opts = variants(base['text'])
        rng = random.Random(int(digest(f'{SEED}|{base["label"]}|{base["text"]}')[:16], 16))
        rng.shuffle(opts)
        count = 0
        for candidate in opts:
            key = normalize(candidate)
            if key in reserved:
                collision_skips += 1
                continue
            if count >= args.variants_per_train_phrase:
                break
            reserved[key].add(base['label'])
            count += 1
            synthetic.append({**base, 'text': candidate, 'is_synthetic': True,
                              'variant_index': count})

    ingredient_rows = original + synthetic
    ingredient_rows.sort(key=lambda r: (('train','validation','test').index(r['split']), r['label'], r['text']))
    for sp in ('train', 'validation', 'test'):
        write_csv(out / 'ingredients' / f'{sp}.csv',
                  (r for r in ingredient_rows if r['split'] == sp), FIELDS)

    # Allergen data is a separate multi-label task; no inferred negatives.
    allergen_rows = []
    parse_errors = 0
    missing_text = 0
    allergen_vocab = Counter()
    allergen_conflicts = defaultdict(set)
    with allergy.open(encoding='utf-8-sig', errors='replace', newline='') as f:
        rd = csv.DictReader(f)
        if not {'ingredient','allergens'}.issubset(rd.fieldnames or []):
            raise SystemExit('Allergen CSV missing ingredient/allergens columns')
        for rownum, r in enumerate(rd, 2):
            phrase = (r.get('ingredient') or '').strip()
            if not phrase:
                missing_text += 1
                continue
            try:
                labels = ast.literal_eval(r.get('allergens') or '')
                if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
                    raise ValueError('Not a list of strings')
            except (ValueError, SyntaxError, TypeError):
                parse_errors += 1
                continue
            labels = sorted({normalize(x) for x in labels if normalize(x)})
            allergen_vocab.update(labels)
            group = digest(normalize(phrase))
            allergen_conflicts[group].add(tuple(labels))
            allergen_rows.append(dict(text=phrase, labels=json.dumps(labels, ensure_ascii=False),
                                      source_id=f'allergy-row-{rownum}', source_row=rownum,
                                      source_file=allergy.name, split=choose_split(group),
                                      is_synthetic=False, license_status='unverified',
                                      source_group=group))
    allergy_fields = ['text','labels','source_id','source_row','source_file','split',
                      'is_synthetic','license_status','source_group']
    for sp in ('train','validation','test'):
        write_csv(out / 'allergens' / f'{sp}.csv',
                  (r for r in allergen_rows if r['split'] == sp), allergy_fields)

    class_splits = defaultdict(Counter)
    original_splits = defaultdict(Counter)
    for r in ingredient_rows:
        class_splits[r['label']][r['split']] += 1
        if not r['is_synthetic']:
            original_splits[r['label']][r['split']] += 1
    class_table = []
    for label in selected:
        c = class_splits[label]
        o = original_splits[label]
        class_table.append(dict(label=label, train=c['train'], validation=c['validation'],
                                test=c['test'], observed_train=o['train'],
                                observed_validation=o['validation'], observed_test=o['test'],
                                synthetic_train=c['train']-o['train'],
                                missing_evaluation_split=(o['validation'] == 0 or o['test'] == 0)))
    write_csv(out / 'reports' / 'class_distribution.csv', class_table,
              ['label','train','validation','test','observed_train','observed_validation',
               'observed_test','synthetic_train','missing_evaluation_split'])
    actual_labels = {r['label'] for r in ingredient_rows}
    no_val = sum(not original_splits[l]['validation'] for l in actual_labels)
    no_test = sum(not original_splits[l]['test'] for l in actual_labels)
    warnings = [
        'Open Food Facts export has no product IDs; exact-phrase grouping is NOT product-independent splitting.',
        'Canonical mappings are weakly supervised, not human-verified; exact phrases may contain noisy/non-ingredient text.',
        'Synthetic edits are heuristic and occur in training only; they are not calibrated using OCR images.',
        'OCR images and existing train/valid/test directories were not modified or evaluated.',
        'Allergen [] means source supplied no labels, not clinically confirmed allergen absence.',
        'Licenses and attribution obligations have not been verified; do not redistribute without review.'
    ]
    if no_val or no_test:
        warnings.append(f'Class coverage inadequate: {no_val} classes lack observed validation, {no_test} lack observed test.')
    if len(ingredient_rows) < args.min_rows or not (args.min_classes <= len(actual_labels) <= args.max_classes):
        warnings.append('Requested target not fully met; no fabricated source records or human-verified labels.')
    report = dict(seed=SEED, method='Exact ingredient phrases and unambiguous E-number/name pairs; weak supervision',
                  source_files={str(p): {'sha256': sha256_file(p), 'size_bytes': p.stat().st_size}
                                for p in (off, allergy)},
                  source_rows=raw_count, observed_unique_phrases=len(observed),
                  candidate_canonical_classes=len(by_label), selected_classes=len(selected),
                  output_classes=len(actual_labels), ingredient_rows=len(ingredient_rows),
                  observed_ingredient_rows=len(original), synthetic_ingredient_rows=len(synthetic),
                  ingredient_split_sizes=dict(Counter(r['split'] for r in ingredient_rows)),
                  observed_split_sizes=dict(Counter(r['split'] for r in original)),
                  ambiguous_e_number_codes=len(ambiguous_codes),
                  conflicting_original_texts=len(conflicts), synthetic_collision_skips=collision_skips,
                  classes_without_observed_validation=no_val, classes_without_observed_test=no_test,
                  allergen_rows=len(allergen_rows), allergen_split_sizes=dict(Counter(r['split'] for r in allergen_rows)),
                  allergen_parse_errors=parse_errors, allergen_missing_text=missing_text,
                  allergen_label_counts=dict(sorted(allergen_vocab.items())),
                  allergen_conflicting_duplicate_texts=sum(len(x)>1 for x in allergen_conflicts.values()),
                  ocr_directory=str(args.ocr), ocr_split_directories=[s for s in ('train','valid','validation','test') if (args.ocr/s).is_dir()],
                  warnings=warnings)
    (out / 'reports').mkdir(parents=True, exist_ok=True)
    (out / 'reports' / 'data_quality.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Ingredient rows:', len(ingredient_rows), 'observed:', len(original), 'synthetic:', len(synthetic))
    print('Classes:', len(actual_labels), '| Allergen rows:', len(allergen_rows))
    print('Report:', out / 'report.json')
    print('WARNING: Experimental weak labels; NOT a leakage-safe or human-validated benchmark.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--ocr', type=Path, default=Path(r'E:\Foodlence\Food Packaging OCR Dataset'))
    p.add_argument('--min-classes', type=int, default=150)
    p.add_argument('--max-classes', type=int, default=200)
    p.add_argument('--min-rows', type=int, default=3000)
    p.add_argument('--variants-per-train-phrase', type=int, default=15)
    p.add_argument('--overwrite', action='store_true', help='Replace V3 outputs only; never inputs or V2')
    args = p.parse_args()
    if args.max_classes < 1 or args.min_classes < 1 or args.variants_per_train_phrase < 0:
        p.error('Class counts must be positive and variants-per-train-phrase nonnegative')
    build(args)


if __name__ == '__main__':
    main()

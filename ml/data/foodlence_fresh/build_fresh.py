#!/usr/bin/env python3
"""Reproducible, fully synthetic FoodLence bootstrap data. Not real-world ground truth."""
import csv, hashlib, json, random, re, argparse
from pathlib import Path
from collections import Counter, defaultdict

SEED=5104
GROUPS={
'grain':'''wheat flour|whole wheat flour|rice flour|corn flour|oat flour|barley flour|rye flour|buckwheat flour|chickpea flour|almond flour|coconut flour|tapioca starch|corn starch|potato starch|modified corn starch|wheat starch|rice starch|semolina|rolled oats|wheat bran|rice bran''',
'sweetener':'''sugar|brown sugar|cane sugar|icing sugar|glucose syrup|fructose|dextrose|maltose|lactose|honey|maple syrup|agave syrup|molasses|invert sugar syrup|corn syrup|rice syrup|date syrup|coconut sugar|malt extract|treacle''',
'oil_fat':'''sunflower oil|palm oil|palm kernel oil|coconut oil|olive oil|soybean oil|canola oil|rapeseed oil|corn oil|sesame oil|peanut oil|cottonseed oil|rice bran oil|safflower oil|avocado oil|cocoa butter|butter|ghee|shortening|vegetable fat''',
'dairy_egg':'''milk powder|skimmed milk powder|whole milk powder|whey powder|whey protein concentrate|milk protein concentrate|casein|sodium caseinate|buttermilk powder|cream powder|cheddar cheese|mozzarella cheese|yogurt powder|milk solids|condensed milk|egg powder|egg white powder|egg yolk powder|liquid egg''',
'plant_protein':'''soy protein isolate|soy protein concentrate|textured soy protein|pea protein|rice protein|wheat gluten|vital wheat gluten|lentil flour|pea flour|soy flour|peanut flour|sunflower protein|pumpkin seed protein|hemp protein|fava bean protein|chickpea protein|potato protein|oat protein|almond protein|sesame protein''',
'herb_spice':'''salt|sea salt|black pepper|white pepper|paprika|turmeric|cumin|coriander|cinnamon|ginger|garlic powder|onion powder|chili powder|cardamom|clove|nutmeg|oregano|basil|thyme|rosemary''',
'fruit_veg':'''tomato paste|tomato powder|apple juice concentrate|lemon juice concentrate|orange juice concentrate|mango puree|banana puree|strawberry puree|raspberry puree|pineapple juice concentrate|carrot powder|beetroot powder|spinach powder|pumpkin puree|onion flakes|garlic puree|potato flakes|cocoa powder|cocoa mass|desiccated coconut''',
'additive':'''citric acid|ascorbic acid|lactic acid|acetic acid|malic acid|tartaric acid|phosphoric acid|sodium benzoate|potassium sorbate|calcium propionate|sodium nitrite|sodium nitrate|monosodium glutamate|xanthan gum|guar gum|locust bean gum|pectin|carrageenan|lecithin|sodium bicarbonate''',
'additive_2':'''calcium carbonate|sodium carbonate|potassium carbonate|calcium chloride|sodium citrate|potassium citrate|sodium lactate|calcium lactate|sorbitol|xylitol|erythritol|sucralose|aspartame|acesulfame potassium|steviol glycosides|silicon dioxide|titanium dioxide|riboflavin|tocopherol|glycerol'''
}
ALLERGENS={
'wheat flour':['wheat','gluten'],'whole wheat flour':['wheat','gluten'],'wheat starch':['wheat','gluten'],'semolina':['wheat','gluten'],'wheat bran':['wheat','gluten'],'wheat gluten':['wheat','gluten'],'vital wheat gluten':['wheat','gluten'],'barley flour':['gluten'],'rye flour':['gluten'],
'almond flour':['tree nuts'],'almond protein':['tree nuts'],'coconut flour':[],'peanut oil':['peanuts'],'peanut flour':['peanuts'],'soybean oil':['soybeans'],'soy protein isolate':['soybeans'],'soy protein concentrate':['soybeans'],'textured soy protein':['soybeans'],'soy flour':['soybeans'],'sesame oil':['sesame'],'sesame protein':['sesame'],
'milk powder':['dairy'],'skimmed milk powder':['dairy'],'whole milk powder':['dairy'],'whey powder':['dairy'],'whey protein concentrate':['dairy'],'milk protein concentrate':['dairy'],'casein':['dairy'],'sodium caseinate':['dairy'],'buttermilk powder':['dairy'],'cream powder':['dairy'],'cheddar cheese':['dairy'],'mozzarella cheese':['dairy'],'yogurt powder':['dairy'],'milk solids':['dairy'],'condensed milk':['dairy'],'cream':['dairy'],'butter':['dairy'],'ghee':['dairy'],'lactose':['dairy'],
'egg powder':['eggs'],'egg white powder':['eggs'],'egg yolk powder':['eggs'],'liquid egg':['eggs']
}
# Three independently generated contexts per class, each with eight variants.
CONTEXTS=[('train','{x}'),('validation','ingredients: {x}'),('test','contains {x}')]
SUBS={'a':'4','e':'3','i':'1','o':'0','s':'5','l':'1'}
def variants(s,rng):
    pool=[s,s.upper(),s.title(),s.replace(' ','  '),s.replace(' ','-'),s.replace(' ','\t')]
    for i,ch in enumerate(s):
        if ch.lower() in SUBS: pool.append(s[:i]+SUBS[ch.lower()]+s[i+1:])
        if i+1<len(s) and s[i].isalpha() and s[i+1].isalpha():pool.append(s[:i]+s[i+1]+s[i]+s[i+2:])
        if i+1<len(s) and s[i].isalpha():pool.append(s[:i]+s[i+1:])
    pool=list(dict.fromkeys(x for x in pool if x.strip()))
    rng.shuffle(pool)
    return [s]+[x for x in pool if x!=s][:7]
def write(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path(__file__).parent/'output');args=p.parse_args()
    out=args.output; rng=random.Random(SEED)
    classes=[(term.strip(),group) for group,block in GROUPS.items() for term in block.split('|')]
    assert len(classes)==180 and len({x for x,_ in classes})==180
    rows=[]; allergen=[]
    for label,category in classes:
        for split,template in CONTEXTS:
            base=template.format(x=label)
            gid='synthetic-'+hashlib.sha256((label+'|'+split).encode()).hexdigest()[:16]
            for idx,text in enumerate(variants(base,rng)):
                row={'text':text,'label':label,'source_id':gid,'source_text':base,'source_type':'model_curated_vocabulary','provenance':'generated_from_embedded_vocabulary','category':category,'split':split,'is_synthetic':'true','variant_index':idx,'annotation_status':'synthetic_not_human_verified','license':'original_generated_dataset'}
                rows.append(row)
                # Only known explicit positive associations; other rows are unknown, not negatives.
                if label in ALLERGENS and ALLERGENS[label]:
                    allergen.append({'text':text,'labels':json.dumps(ALLERGENS[label]),'source_id':gid,'split':split,'is_synthetic':'true','label_status':'rule_based_positive_only','provenance':'embedded_explicit_associations'})
    # No conflicting phrase-label mappings. Discard all collisions, do not choose arbitrary truth.
    owners=defaultdict(set)
    for r in rows:owners[re.sub(r'\s+',' ',r['text'].lower()).strip()].add(r['label'])
    conflicts={k for k,v in owners.items() if len(v)>1}
    rows=[r for r in rows if re.sub(r'\s+',' ',r['text'].lower()).strip() not in conflicts]
    seen=set(); dedup=[]
    for r in rows:
        k=(r['split'],r['label'],r['text'])
        if k not in seen:dedup.append(r);seen.add(k)
    rows=dedup
    for split,_, in CONTEXTS:
        subset=[r for r in rows if r['split']==split]
        write(out/'ingredients'/f'{split}.csv',subset,list(rows[0]))
        write(out/'allergens'/f'{split}.csv',[r for r in allergen if r['split']==split],list(allergen[0]))
    write(out/'class_counts.csv',[{'label':l,'category':c,'train':sum(r['label']==l and r['split']=='train' for r in rows),'validation':sum(r['label']==l and r['split']=='validation' for r in rows),'test':sum(r['label']==l and r['split']=='test' for r in rows)} for l,c in classes],['label','category','train','validation','test'])
    report={'seed':SEED,'canonical_classes':len(classes),'ingredient_rows':len(rows),'ingredient_split_sizes':dict(Counter(r['split'] for r in rows)),'allergen_positive_rows':len(allergen),'allergen_split_sizes':dict(Counter(r['split'] for r in allergen)),'conflicting_texts_removed':len(conflicts),'all_synthetic':True,'provenance':'Original embedded, model-curated vocabulary; no Open Food Facts, OCR images, or allergies_10k source rows used','limitations':['Not human verified','No real packaging observations','Validation and test are synthetic contexts, not independent real-world generalization benchmarks','Allergen set contains positive-only examples; absence is unknown','OCR perturbations are heuristic and not empirically calibrated','Source IDs refer to generated template groups, not real products'],'license':'Original generated data; third-party trademark/source claims not asserted'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (out/'README.md').write_text('# FoodLence synthetic bootstrap dataset\n\n180 canonical labels, 3 template contexts per class, up to 8 variants per context. All rows synthetic, including clean templates. Train/validation/test separated by template group, but share class names: **not an independent benchmark**. Allergen CSV contains only explicit positive associations; do not interpret unlisted allergens as negative. Run `python build_fresh.py --output output`. No source datasets are read.\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()

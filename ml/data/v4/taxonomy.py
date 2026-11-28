"""Curated FoodLence taxonomy foundation.

Names are sourced from the existing synthetic development vocabulary. Entries
are marked unverified because the repository contains no authoritative class
taxonomy or completed knowledge-base seed files.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxonomyClass:
    class_id: str
    canonical_name: str
    type: str
    category: str
    aliases: tuple[str, ...] = ()
    e_number: str = ""
    description: str = ""
    taxonomy_source: str = "foodlence_fresh/build_fresh.py embedded vocabulary"
    verification_status: str = "unverified"


_GROUPS = {
    "grain": "wheat flour|whole wheat flour|rice flour|corn flour|oat flour|barley flour|rye flour|buckwheat flour|chickpea flour|almond flour|coconut flour|tapioca starch|corn starch|potato starch|modified corn starch|wheat starch|rice starch|semolina|rolled oats|wheat bran|rice bran",
    "sweetener": "sugar|brown sugar|cane sugar|icing sugar|glucose syrup|fructose|dextrose|maltose|lactose|honey|maple syrup|agave syrup|molasses|invert sugar syrup|corn syrup|rice syrup|date syrup|coconut sugar|malt extract|treacle",
    "oil_fat": "sunflower oil|palm oil|palm kernel oil|coconut oil|olive oil|soybean oil|canola oil|rapeseed oil|corn oil|sesame oil|peanut oil|cottonseed oil|rice bran oil|safflower oil|avocado oil|cocoa butter|butter|ghee|shortening|vegetable fat",
    "dairy_egg": "milk powder|skimmed milk powder|whole milk powder|whey powder|whey protein concentrate|milk protein concentrate|casein|sodium caseinate|buttermilk powder|cream powder|cheddar cheese|mozzarella cheese|yogurt powder|milk solids|condensed milk|egg powder|egg white powder|egg yolk powder|liquid egg",
    "plant_protein": "soy protein isolate|soy protein concentrate|textured soy protein|pea protein|rice protein|wheat gluten|vital wheat gluten|lentil flour|pea flour|soy flour|peanut flour|sunflower protein|pumpkin seed protein|hemp protein|fava bean protein|chickpea protein|potato protein|oat protein|almond protein|sesame protein",
    "herb_spice": "salt|sea salt|black pepper|white pepper|paprika|turmeric|cumin|coriander|cinnamon|ginger|garlic powder|onion powder|chili powder|cardamom|clove|nutmeg|oregano|basil|thyme|rosemary",
    "fruit_veg": "tomato paste|tomato powder|apple juice concentrate|lemon juice concentrate|orange juice concentrate|mango puree|banana puree|strawberry puree|raspberry puree|pineapple juice concentrate|carrot powder|beetroot powder|spinach powder|pumpkin puree|onion flakes|garlic puree|potato flakes|cocoa powder|cocoa mass|desiccated coconut",
    "additive": "citric acid|ascorbic acid|lactic acid|acetic acid|malic acid|tartaric acid|phosphoric acid|sodium benzoate|potassium sorbate|calcium propionate|sodium nitrite|sodium nitrate|monosodium glutamate|xanthan gum|guar gum|locust bean gum|pectin|carrageenan|lecithin|sodium bicarbonate",
    "additive_2": "calcium carbonate|sodium carbonate|potassium carbonate|calcium chloride|sodium citrate|potassium citrate|sodium lactate|calcium lactate|sorbitol|xylitol|erythritol|sucralose|aspartame|acesulfame potassium|steviol glycosides|silicon dioxide|titanium dioxide|riboflavin|tocopherol|glycerol",
}


def load_taxonomy() -> tuple[TaxonomyClass, ...]:
    entries = []
    for category, names in _GROUPS.items():
        kind = "additive" if category.startswith("additive") else "ingredient"
        for name in names.split("|"):
            canonical = name.strip().lower()
            entries.append(TaxonomyClass(
                class_id=f"FL-{len(entries) + 1:03d}", canonical_name=canonical,
                type=kind, category=category,
                description=f"Canonical label: {canonical}.",
            ))
    return tuple(entries)


TAXONOMY = load_taxonomy()

import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.allergen import Allergen
from app.models.ingredient import Ingredient
from app.models.additive import Additive

# Built-in high-fidelity Allergen Knowledge Base Taxonomy (FDA Big 9 + EU 14)
CORE_ALLERGEN_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "peanut": {
        "name": "Peanuts",
        "synonyms": ["peanut", "peanuts", "groundnut", "groundnuts", "arachis oil", "goober", "monkey nuts"],
        "default_severity": "severe",
    },
    "tree_nuts": {
        "name": "Tree Nuts",
        "synonyms": [
            "almond", "almonds", "hazelnut", "hazelnuts", "walnut", "walnuts",
            "cashew", "cashews", "pecan", "pecans", "brazil nut", "pistachio",
            "pistachios", "macadamia", "chestnut", "praline", "marzipan"
        ],
        "default_severity": "severe",
    },
    "milk": {
        "name": "Milk & Dairy",
        "synonyms": [
            "milk", "dairy", "casein", "caseinate", "whey", "lactose", "curd",
            "butter", "ghee", "cream", "lactalbumin", "yogurt", "cheese",
            "milk solids", "skimmed milk", "whole milk powder", "milk fat"
        ],
        "default_severity": "moderate",
    },
    "egg": {
        "name": "Eggs",
        "synonyms": [
            "egg", "eggs", "albumin", "ovalbumin", "egg yolk", "egg white",
            "lysozyme", "mayonnaise", "meringue", "surimi", "globulin"
        ],
        "default_severity": "severe",
    },
    "gluten": {
        "name": "Wheat & Gluten",
        "synonyms": [
            "wheat", "wheat flour", "gluten", "barley", "rye", "malt", "spelt",
            "semolina", "durum", "bulgur", "farina", "triticale", "couscous", "seitan"
        ],
        "default_severity": "severe",
    },
    "soy": {
        "name": "Soy & Soybeans",
        "synonyms": [
            "soy", "soya", "soybean", "soybeans", "edamame", "tofu", "tempeh",
            "soy lecithin", "textured vegetable protein", "tvp", "miso", "natto", "shoyu"
        ],
        "default_severity": "moderate",
    },
    "fish": {
        "name": "Fish",
        "synonyms": [
            "fish", "cod", "salmon", "tuna", "tilapia", "bass", "anchovy", "anchovies",
            "fish sauce", "isinglass", "surimi", "caviar"
        ],
        "default_severity": "severe",
    },
    "shellfish": {
        "name": "Crustacean & Molluscan Shellfish",
        "synonyms": [
            "shellfish", "shrimp", "prawn", "prawns", "crab", "lobster", "crayfish",
            "clam", "clams", "mussel", "mussels", "oyster", "oysters", "scallop",
            "scallops", "squid", "calamari", "octopus", "cuttlefish"
        ],
        "default_severity": "severe",
    },
    "sesame": {
        "name": "Sesame",
        "synonyms": ["sesame", "sesame seed", "sesame seeds", "tahini", "sesamol", "gingelly", "til"],
        "default_severity": "severe",
    },
    "sulfites": {
        "name": "Sulfites",
        "synonyms": ["sulfite", "sulfites", "sulphite", "sulphites", "sulfur dioxide", "sodium bisulfite", "metabisulfite"],
        "default_severity": "moderate",
    },
    "mustard": {
        "name": "Mustard",
        "synonyms": ["mustard", "mustard seed", "mustard powder", "dijon"],
        "default_severity": "moderate",
    },
    "celery": {
        "name": "Celery",
        "synonyms": ["celery", "celery root", "celeriac", "celery salt"],
        "default_severity": "mild",
    },
}

# Known additive directory
KNOWN_ADDITIVES: Dict[str, Dict[str, str]] = {
    "E102": {"name": "Tartrazine", "category": "Color", "risk": "caution", "explanation": "Synthetic lemon yellow azo dye linked to hyperactivity and asthma triggers."},
    "E110": {"name": "Sunset Yellow FCF", "category": "Color", "risk": "caution", "explanation": "Petroleum-derived orange azo dye; potential allergen trigger."},
    "E129": {"name": "Allura Red AC", "category": "Color", "risk": "caution", "explanation": "Red azo dye; monitored for hyperactivity in sensitive individuals."},
    "E211": {"name": "Sodium Benzoate", "category": "Preservative", "risk": "caution", "explanation": "Common food preservative; can form benzene when combined with Vitamin C."},
    "E322": {"name": "Lecithin", "category": "Emulsifier", "risk": "caution", "explanation": "Natural emulsifier, typically extracted from Soy or Egg."},
    "E330": {"name": "Citric Acid", "category": "Acidity Regulator", "risk": "safe", "explanation": "Naturally occurring organic acid used for preservation and tart flavor."},
    "E621": {"name": "Monosodium Glutamate (MSG)", "category": "Flavor Enhancer", "risk": "caution", "explanation": "Glutamic acid sodium salt; can induce headaches in glutamate-sensitive individuals."},
    "E951": {"name": "Aspartame", "category": "Sweetener", "risk": "caution", "explanation": "Non-nutritive artificial sweetener; unsafe for individuals with Phenylketonuria (PKU)."},
}


class AllergenEngine:
    """
    Evaluates detected ingredients against the knowledge base and user dietary profiles
    to produce deterministic safety verdicts.
    """

    @classmethod
    def match_allergens_for_ingredients(
        cls,
        ingredients: List[str],
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Cross-references ingredient strings against the allergen taxonomy.
        """
        matches: List[Dict[str, Any]] = []
        seen_keys = set()

        for ing in ingredients:
            ing_lower = ing.lower().strip()

            # 1. Match against Core Taxonomy
            for code, data in CORE_ALLERGEN_TAXONOMY.items():
                for syn in data["synonyms"]:
                    pattern = rf"\b{re.escape(syn)}\b"
                    if re.search(pattern, ing_lower):
                        key = (code, ing)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            matches.append({
                                "allergen_code": code,
                                "allergen_name": data["name"],
                                "severity_default": data["default_severity"],
                                "cross_reactivity": "direct" if syn == code or syn in ing_lower else "cross_reactive",
                                "matched_ingredient": ing,
                            })
                        break

            # 2. Match against Database if DB session is active
            if db is not None:
                try:
                    db_ing = db.query(Ingredient).filter(
                        Ingredient.standard_name.ilike(f"%{ing_lower}%")
                    ).first()
                    if db_ing and db_ing.allergen_mappings:
                        for mapping in db_ing.allergen_mappings:
                            key = (mapping.allergen.allergen_code, ing)
                            if key not in seen_keys:
                                seen_keys.add(key)
                                matches.append({
                                    "allergen_code": mapping.allergen.allergen_code,
                                    "allergen_name": mapping.allergen.allergen_name,
                                    "severity_default": mapping.allergen.severity_default,
                                    "cross_reactivity": mapping.cross_reactivity_risk,
                                    "matched_ingredient": ing,
                                })
                except Exception:
                    pass

        return matches

    @classmethod
    def match_additives(cls, additive_codes: List[str], db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """
        Looks up metadata for detected E-numbers.
        """
        results: List[Dict[str, Any]] = []
        for code in additive_codes:
            clean_code = code.upper().strip()
            if clean_code in KNOWN_ADDITIVES:
                data = KNOWN_ADDITIVES[clean_code]
                results.append({
                    "e_number": clean_code,
                    "name": data["name"],
                    "category": data["category"],
                    "risk_level": data["risk"],
                    "explanation": data["explanation"],
                    "health_concerns": None,
                })
            elif db is not None:
                try:
                    db_add = db.query(Additive).filter(Additive.e_number == clean_code).first()
                    if db_add:
                        results.append({
                            "e_number": db_add.e_number,
                            "name": db_add.standard_name,
                            "category": db_add.category,
                            "risk_level": db_add.risk_level,
                            "explanation": db_add.explanation,
                            "health_concerns": db_add.health_concerns,
                        })
                except Exception:
                    pass

        return results

    @classmethod
    def evaluate_safety_verdict(
        cls,
        matched_allergens: List[Dict[str, Any]],
        detected_additives: List[Dict[str, Any]],
        profile_allergens: Optional[List[Dict[str, Any]]] = None,
        profile_name: str = "Active Profile",
    ) -> Tuple[str, str, str, List[Dict[str, Any]]]:
        """
        Computes deterministic safety verdict: (safety_verdict, verdict_color, summary, evaluated_allergens).
        """
        if profile_allergens is None:
            profile_allergens = []

        # Map profile allergens by normalized code / name
        user_allergen_map: Dict[str, str] = {}
        for item in profile_allergens:
            code = item.get("allergen_id") or item.get("id") or item.get("allergen_code") or ""
            name = item.get("name") or item.get("allergen_name") or ""
            severity = item.get("severity") or "severe"
            if code:
                user_allergen_map[str(code).lower().strip()] = severity
            if name:
                user_allergen_map[str(name).lower().strip()] = severity

        conflicts: List[Dict[str, Any]] = []
        evaluated_allergens: List[Dict[str, Any]] = []

        for match in matched_allergens:
            code = match["allergen_code"].lower()
            name = match["allergen_name"].lower()

            is_conflict = False
            user_severity = match["severity_default"]

            # Check if user has this allergen
            for u_key, u_sev in user_allergen_map.items():
                if u_key in code or u_key in name or code in u_key:
                    is_conflict = True
                    user_severity = u_sev
                    break

            evaluated_item = {
                **match,
                "severity_level": user_severity,
                "is_profile_conflict": is_conflict,
            }
            evaluated_allergens.append(evaluated_item)
            if is_conflict:
                conflicts.append(evaluated_item)

        # Verdict calculation
        if conflicts:
            severe_conflicts = [c for c in conflicts if str(c.get("severity_level", "")).lower() == "severe"]
            if severe_conflicts:
                names = ", ".join({c["allergen_name"] for c in severe_conflicts})
                return (
                    "UNSAFE",
                    "red",
                    f"DANGER: Contains {names}, which poses a severe allergic risk for {profile_name}.",
                    evaluated_allergens,
                )
            else:
                names = ", ".join({c["allergen_name"] for c in conflicts})
                return (
                    "CAUTION",
                    "yellow",
                    f"WARNING: Contains {names}, which triggers dietary warnings for {profile_name}.",
                    evaluated_allergens,
                )

        # Check for caution-level additives if no allergen conflicts exist
        caution_additives = [a for a in detected_additives if a.get("risk_level") in ("caution", "danger")]
        if caution_additives:
            add_names = ", ".join({a["name"] for a in caution_additives[:2]})
            return (
                "CAUTION",
                "yellow",
                f"No major profile allergens detected, but contains additives ({add_names}) that may cause sensitivity.",
                evaluated_allergens,
            )

        if matched_allergens:
            all_names = ", ".join({a["allergen_name"] for a in matched_allergens[:3]})
            return (
                "SAFE",
                "green",
                f"SAFE for {profile_name}. (General allergens present: {all_names}, but none conflict with active profile).",
                evaluated_allergens,
            )

        return (
            "SAFE",
            "green",
            f"SAFE: No conflicting allergens or hazardous food additives detected for {profile_name}.",
            evaluated_allergens,
        )


allergen_engine = AllergenEngine()

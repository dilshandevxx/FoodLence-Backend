-- =============================================================================
--  FoodLence Knowledge Base Seed — Allergen Groups & Taxonomies
--  Target Table: kb.allergen_groups, kb.additive_categories
--  Owner: S.K.P.H. Deemantha (22CSE0348) — Knowledge Base Lead
--  Regulatory Standards: FDA FALCPA/FASTER Act, EU FIC Regulation 1169/2011, CODEX STAN 1-1985
-- =============================================================================

-- Ensure schema exists
CREATE SCHEMA IF NOT EXISTS kb;

-- -----------------------------------------------------------------------------
-- 1. Allergen Groups (9 Major FDA/EU Allergens + Sulfite Group)
-- -----------------------------------------------------------------------------
INSERT INTO kb.allergen_groups (code, name, description, is_major, icon_code, display_order, is_active)
VALUES
    ('PEANUT',
     'Peanut',
     'Peanut (groundnut, Arachis hypogaea) and all derivatives including peanut butter, peanut flour, and unrefined peanut oil. One of the most common causes of severe anaphylaxis.',
     true,
     'peanut',
     1,
     true),

    ('TREE_NUT',
     'Tree nuts',
     'Botanical tree nuts including almond, cashew, hazelnut, walnut, pistachio, pecan, macadamia, brazil nut, and pine nuts. Highly potent allergen causing life-threatening reactions.',
     true,
     'tree-nut',
     2,
     true),

    ('MILK',
     'Milk',
     'Cow milk and other animal milk, along with derivatives such as casein, whey, lactose, butter, ghee, and curd. Distinct from lactose intolerance; involves immunological response.',
     true,
     'milk',
     3,
     true),

    ('EGG',
     'Egg',
     'Poultry eggs and derived proteins including ovalbumin, ovotransferrin, lysozyme, and egg powder. Frequent trigger of allergic reactions in children.',
     true,
     'egg',
     4,
     true),

    ('SOY',
     'Soy',
     'Soybean (Glycine max) and soy-derived proteins, soy lecithin, miso, tofu, and edamame. Major plant-based allergen prevalent across processed snacks and baked goods.',
     true,
     'soy',
     5,
     true),

    ('WHEAT',
     'Wheat',
     'Wheat species (common wheat, durum, spelt, kamut, emmer, einkorn, semolina, farina) containing gluten and non-gluten proteins. Covers IgE-mediated wheat allergy.',
     true,
     'wheat',
     6,
     true),

    ('FISH',
     'Fish',
     'Finned fish species (e.g., cod, salmon, tuna, anchovy, mackerel) and derived products such as fish sauce and isinglass. High cross-reactivity between different finfish species.',
     true,
     'fish',
     7,
     true),

    ('SHELLFISH',
     'Shellfish',
     'Crustacean shellfish (shrimp, prawn, crab, lobster, krill) and molluscan shellfish (squid, oyster, mussel, clam). Primarily driven by muscle protein tropomyosin.',
     true,
     'shellfish',
     8,
     true),

    ('SESAME',
     'Sesame',
     'Sesame seed (Sesamum indicum) and derived products including tahini, sesame flour, and cold-pressed sesame (gingelly) oil. Recognized as the 9th major US allergen under the FASTER Act (2023).',
     true,
     'sesame',
     9,
     true),

    ('SULFITE',
     'Sulfites',
     'Sulfur dioxide and inorganic sulfite salts (E220 to E228) used as preservatives in dried fruit, wine, processed juices, and syrups. Can induce acute bronchospasm in asthmatic consumers (>10 ppm).',
     false,
     'sulfite',
     10,
     true)
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_major = EXCLUDED.is_major,
    icon_code = EXCLUDED.icon_code,
    display_order = EXCLUDED.display_order,
    is_active = EXCLUDED.is_active,
    updated_at = now();

-- -----------------------------------------------------------------------------
-- 2. Additive Functional Categories (CODEX / EFSA Classification)
-- -----------------------------------------------------------------------------
INSERT INTO kb.additive_categories (code, name, description)
VALUES
    ('PRESERVATIVE',
     'Preservative',
     'Substances that prolong the shelf life of foods by protecting them against deterioration caused by microorganisms (E200-E299).'),

    ('COLOUR',
     'Colour',
     'Substances that add or restore color in a food, including natural pigments and synthetic dyes (E100-E199).'),

    ('SWEETENER',
     'Sweetener',
     'Non-sugar substances that impart a sweet taste to foods, often with low or zero caloric value (E950-E969).'),

    ('EMULSIFIER',
     'Emulsifier',
     'Substances that make it possible to form or maintain a uniform mixture of two or more immiscible phases, such as oil and water (E322, E471).'),

    ('STABILISER',
     'Stabiliser',
     'Substances that maintain the physical-chemical state of a foodstuff, including stabilizers of emulsions and suspensions.'),

    ('FLAVOUR_ENHANCER',
     'Flavour enhancer',
     'Substances that enhance the existing taste and/or odor of a foodstuff (E620-E640, e.g., Monosodium Glutamate).'),

    ('ANTIOXIDANT',
     'Antioxidant',
     'Substances that prolong the shelf life of foods by protecting them against deterioration caused by oxidation, such as fat rancidity and color changes (E300-E321).'),

    ('ACIDITY_REGULATOR',
     'Acidity regulator',
     'Substances that alter or control the acidity or alkalinity of a foodstuff (E260, E330, E500).'),

    ('THICKENER',
     'Thickener',
     'Substances that increase the viscosity of a foodstuff without substantially altering its other properties (E400-E440, e.g., gums and pectins).'),

    ('RAISING_AGENT',
     'Raising agent',
     'Substances or combinations of substances that liberate gas and thereby increase the volume of a dough or batter (E500, E503).')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description;

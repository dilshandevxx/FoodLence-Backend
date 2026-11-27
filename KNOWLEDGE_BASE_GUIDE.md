# FoodLence Knowledge Base & Database Layer — Developer & Module Specification

**SE5104 Mini Project — Group 14**  
**Faculty of Computing, Sabaragamuwa University of Sri Lanka**  
**Academic Year**: 2022 / 2023  
**Module Lead & Owner**: S.K.P.H. Deemantha (`22CSE0348`) — Knowledge Base Lead (Developer C / Member 3)  
**Assigned Contribution**: 25%  
**Internal Supervisor**: Ms. B.R. Madhurangi (Lecturer)  
**Industry Mentor**: Mr. G.A.C.G. Dhanawardhana (Associate Software Engineer, LSEG Technology / Surecore)  
**Target RDBMS**: PostgreSQL 15+ (Production: Managed Neon Serverless PG16)

---

## 1. Executive Summary & Proposal Traceability

This document constitutes the official module specification, scientific curation manual, and academic defense guide for **S.K.P.H. Deemantha (Member 3 / Developer C)** as mandated by the *FoodLence - AI-Based Food Label Scanner* Project Proposal.

### 1.1. Module Ownership Matrix (Proposal Section 1 & Table 1)
| Member | Registration | Project Role | Module Ownership | Contribution |
| :--- | :--- | :--- | :--- | :--- |
| H.G.B.A. Mekala | `22CSE0361` | Developer A (Mobile & UI Lead) | Flutter Client, Scanner UI, History Screens, Result Dashboard | 25% |
| H.G.K. Rashmika | `21CSE0190` | Developer B (ML Lead) | OCR-Noise Dataset, spaCy/scikit-learn Classifier, F1 Optimization | 25% |
| **S.K.P.H. Deemantha** | **`22CSE0348`** | **Developer C (Knowledge Base Lead)** | **PostgreSQL 3NF Schema, Chemical/E-Number Mappings, Translation Query Layer, Curation Docs** | **25%** |
| P.A.A. Ishara Dilshan | `22CSE0360` | Developer D (Backend Lead) | FastAPI REST Service, JWT Auth, Docker, Cloud CI/CD Deployment | 25% |

### 1.2. Direct Mapping to Proposal Objectives & Deliverables
* **Proposal Section 1.3 (Member 3 Responsibilities)**:
  * Design and maintain the relational PostgreSQL database schema (entities, synonyms, E-numbers, allergen groups).
  * Curate scientific mappings from FDA, EFSA, and CODEX covering the 9 major allergens + sulfite group ($E220\text{--}E228 \rightarrow \text{sulfite}$; $\text{casein/whey/E322} \rightarrow \text{milk/soy}$).
  * Engineer the database translation query layer resolving predicted entities into allergen warnings, additive functional categories, and plain-language explanations.
* **Proposal Section 1.3 Deliverables**:
  1. **Populated Knowledge Base**: 300+ standardized food entities, 100+ additives with E-numbers *(Supplied in `knowledge_base_seed/` & `app/db/02_seed_reference.sql`)*.
  2. **Translation Query Layer**: Stored functions `kb.fn_resolve_ingredients()`, `kb.fn_match_ingredient()`, and `app.fn_evaluate_scan()`.
  3. **Curation Documentation**: This comprehensive guide detailing curation standards, taxonomies, and schema decisions.
* **Proposal Section 4.2 (Objective 4 & 5)**:
  * *Objective 4*: Relational Knowledge Base Construction (Highly normalized PostgreSQL database semantically mapping chemical names, alternative terminology, and E-numbers to the 9 major allergens).
  * *Objective 5*: Semantic Translation & Personalized Evaluation (FastAPI cross-referencing against PostgreSQL knowledge base and user dietary profiles).
* **Proposal Section 13.2 & 13.3 (Timeline & Milestones)**:
  * *Phase 3 (Weeks 4-6)*: ML Model Training and Database Schema Construction.
  * *Milestone 3*: Functional PostgreSQL knowledge base accurately translating chemical entities to major allergen groups.

---

## 2. System Architecture & Schema Specification

The database architecture deprecates the initial draft's monolithic offline approach in favor of an enterprise 3-schema decoupled model:
1. `kb` (**Knowledge Base Schema**): Authoritative scientific dictionary containing canonical food ingredients, chemical synonyms/aliases, E-number additives, and regulatory allergen associations.
2. `app` (**Application Schema**): Transactional data handling users, JWT session refresh tokens, family allergen profiles, multi-level scan logs, and parsed ingredient fragments.
3. `audit` (**Audit Schema**): High-integrity, append-only changelog capturing all inserts, updates, and deletes across the knowledge base with actor attribution (`app.actor`).

```
                ┌─────────────────────────────────────────────────────────────┐
                │                     PostgreSQL Database                     │
                ├──────────────────────┬──────────────────────┬───────────────┤
                │      Schema kb       │      Schema app      │ Schema audit  │
                ├──────────────────────┼──────────────────────┼───────────────┤
                │ allergen_groups      │ users                │ kb_change_log │
                │ additive_categories  │ roles                │               │
                │ ingredients          │ user_roles           │               │
                │ additive_details     │ refresh_tokens       │               │
                │ ingredient_allergens │ profiles             │               │
                │ ingredient_aliases   │ profile_allergens    │               │
                │                      │ profile_additives    │               │
                │                      │ scans                │               │
                │                      │ scan_ingredients     │               │
                │                      │ scan_matches         │               │
                │                      │ v_inference_logs (V) │               │
                └──────────────────────┴──────────────────────┴───────────────┘
```

### 2.1. 3NF Normalization vs. Proposal Draft (Viva Voce Defense)
In the initial project proposal draft (Section 7.5, Tables 3, 4, 6), several columns were loosely typed as `JSONB` arrays (e.g., `Profiles.active_allergens JSONB`, `Ingredients.alternative_names JSONB`, `Inference_Logs.predicted_entities JSONB`). 

Member 3 deliberately re-engineered the physical schema into **Third Normal Form (3NF)**:
1. **Referential Integrity**: Storing foreign keys in junction tables (`app.profile_allergens`, `kb.ingredient_aliases`, `kb.ingredient_allergens`) guarantees that allergen IDs and alias records can never be orphaned or corrupted.
2. **Indexing & Search Acceleration**: Storing aliases as discrete rows in `kb.ingredient_aliases` allows indexing via PostgreSQL Trigram GIN indexes (`gin_trgm_ops`). This enables millisecond-level fuzzy matching for OCR corruptions (e.g., `"cas1en" \rightarrow "casein"`), which is impossible inside an unindexed JSONB array.
3. **Subtype Specialization**: Additives are modeled as a 1:1 subtype table `kb.additive_details` inheriting from `kb.ingredients`. Because Developer B's ML classifier outputs both standard ingredients and E-numbers as standardized entity slugs, a unified dictionary provides a single resolution path while keeping additive-specific columns (`e_number`, `concern_level`, `additive_category_id`) non-sparse and clean.
4. **Tenant Isolation**: `app.scans` enforces a composite foreign key `(profile_id, user_id) REFERENCES app.profiles(profile_id, user_id)`, guaranteeing that User A can never attach or evaluate a scan against User B's profile.

---

## 3. Database Entity Catalog & Dictionary

### 3.1. Knowledge Base Entities (`kb`)

#### 1. `kb.allergen_groups`
Stores the internationally regulated major allergen groups.
* `allergen_group_id` (`smallint`, PK): Identity key.
* `code` (`varchar(30)`, UNIQUE): Regulatory mnemonic (`PEANUT`, `TREE_NUT`, `MILK`, `EGG`, `SOY`, `WHEAT`, `FISH`, `SHELLFISH`, `SESAME`, `SULFITE`).
* `name` (`varchar(80)`): Plain-language display name.
* `description` (`text`): Clinical summary of the allergen group.
* `is_major` (`boolean`): Flags the FDA/EU top-tier allergens.
* `icon_code` (`varchar(50)`): Mobile UI asset mapping icon.
* `display_order` (`smallint`): Ordering in profile selection UI.

#### 2. `kb.additive_categories`
Stores functional classes defined by CODEX Alimentarius.
* `additive_category_id` (`smallserial`, PK): Serial identifier.
* `code` (`varchar(40)`, UNIQUE): Functional category code (`PRESERVATIVE`, `COLOUR`, `SWEETENER`, `EMULSIFIER`, `STABILISER`, `FLAVOUR_ENHANCER`, `ANTIOXIDANT`, `ACIDITY_REGULATOR`, `THICKENER`, `RAISING_AGENT`).
* `name` (`varchar(80)`): Human-readable category label.
* `description` (`text`): Functional definition.

#### 3. `kb.ingredients` (Supertype Table)
Primary lexicon of standardized food ingredients and additives.
* `ingredient_id` (`uuid`, PK): Default `gen_random_uuid()`.
* `slug` (`varchar(80)`, UNIQUE): **Immutable contract with ML team** (e.g., `sodium_caseinate`, `whey`, `e322_lecithin`). Pattern: `^[a-z0-9]+(_[a-z0-9]+)*$`.
* `canonical_name` (`citext`, UNIQUE): Clean display name.
* `normalised_name` (`text`, GENERATED STORED): Deterministic normalization using `kb.normalise_text()` (strips punctuation, percentages, diacritics, and whitespace).
* `ingredient_type` (`kb.ingredient_type` ENUM): `'allergen_source'`, `'additive'`, or `'neutral'`.
* `explanation` (`text`): Consumer-friendly educational explanation (Proposal Section 6.2 & 6.4).
* `is_active` (`boolean`): Soft deletion flag.

#### 4. `kb.additive_details` (1:1 Subtype Table)
Detailed metadata for ingredients classified as food additives.
* `ingredient_id` (`uuid`, PK): Foreign key to `kb.ingredients(ingredient_id) ON DELETE CASCADE`.
* `e_number` (`varchar(15)`, UNIQUE): European additive code (e.g., `E322`, `E223`, `E1105`).
* `additive_category_id` (`smallint`, FK): Links to `kb.additive_categories`.
* `concern_level` (`smallint`): Safety rating (1 = Low/Safe, 2 = Moderate/Caution, 3 = High Concern/Restricted).

#### 5. `kb.ingredient_allergens` (Junction Table)
Many-to-many semantic translation mapping ingredients/additives to allergen groups.
* `ingredient_id` (`uuid`, FK): Links to `kb.ingredients`.
* `allergen_group_id` (`smallint`, FK): Links to `kb.allergen_groups`.
* `certainty` (`kb.allergen_certainty` ENUM):
  * `definite`: Ingredient is or contains the protein (e.g., `sodium_caseinate` $\rightarrow$ `MILK`).
  * `probable`: Commonly derived from the allergen (e.g., `e322_lecithin` $\rightarrow$ `SOY`).
  * `possible`: Derivative may contain trace fractions depending on manufacturing source.
* `source` (`kb.source_authority` ENUM): Authority citation (`FDA`, `EFSA`, `CODEX`, `MANUFACTURER`, `TEAM_REVIEW`).
* `note` (`text`): Regulatory citation or rationale.

#### 6. `kb.ingredient_aliases`
Comprehensive dictionary of commercial brand names, chemical variants, and common OCR corruptions.
* `alias_id` (`uuid`, PK): Unique alias identifier.
* `ingredient_id` (`uuid`, FK): Target canonical ingredient.
* `alias_text` (`citext`): Surface form (e.g., `"soya"`, `"maida"`, `"gingelly oil"`, `"caseinate"`).
* `normalised_alias` (`text`, GENERATED STORED): Lowercased, unaccented, punctuation-stripped string with unique index `uq_alias_normalised`.

---

### 3.2. Application & Transactional Entities (`app`)

#### 1. `app.users` & `app.refresh_tokens`
* Stores user credentials (bcrypt password hashes) and mandatory medical disclaimer acceptance timestamp (`disclaimer_accepted_at`) fulfilling Proposal Sections 10.4 & 14.4.
* `app.refresh_tokens` implements cryptographic token rotation and revocation on logout (Proposal Section 7.6 & 10.3).

#### 2. `app.profiles`, `app.profile_allergens`, `app.profile_additives`
* Implements multi-profile dietary management (up to 5 profiles per user enforced by trigger `app.fn_limit_profiles_per_user()`, FR-08).
* Allows assigning discrete severity ratings (`mild`, `moderate`, `severe`) per allergen.
* Enables health-conscious users to flag unwanted additives (e.g., avoiding artificial colorants or high-concern preservatives).

#### 3. `app.scans`, `app.scan_ingredients`, `app.scan_matches`
* Implements the scan persistence and continuous learning feedback loop (FR-09, Proposal Section 9.4).
* Stores raw noisy OCR strings (`raw_ocr_text`), model confidence scores, processing latency, and overall safety determinations.
* Deconstructs raw label text into structured fragments (`app.scan_ingredients`) with hierarchical nesting depth (e.g., `chocolate (sugar, milk solids, emulsifier (soy lecithin))`).
* Flags precautionary manufacturer statements (`is_precautionary = true`) for *"May contain traces of..."* to prevent false-positive panic.
* Exposes `app.v_inference_logs` view directly to Developer B for harvesting real-world OCR failures and retraining the NLP model.

---

## 4. Scientific Curation Protocol (FDA / EFSA / CODEX)

### 4.1. The "Big 9" + Sulfites Taxonomy

FoodLence standardizes across international food safety standards:
1. **Peanut (`PEANUT`)**: Covers *Arachis hypogaea*, peanut butter, peanut flour, and unrefined arachis oil (Ara h 1-17).
2. **Tree Nuts (`TREE_NUT`)**: Covers botanical tree nuts: Almond (*Prunus dulcis*), Cashew (*Anacardium occidentale*), Walnut (*Juglans regia*), Hazelnut/Filbert (*Corylus avellana*), Pistachio, Pecan, Macadamia, Brazil nut, and Pine nuts.
3. **Milk (`MILK`)**: Covers bovine milk and derived proteins: Casein (alpha-, beta-, kappa-casein), Sodium Caseinate, Calcium Caseinate, Whey, Whey Protein Concentrate/Isolate, Lactalbumin, Lactoglobulin, Butter, Ghee, and Curd.
4. **Egg (`EGG`)**: Covers poultry eggs and fractions: Ovalbumin (Gal d 2), Ovotransferrin (Gal d 3), Ovomucoid (Gal d 1), Ovomucin, Vitellin, Livetin, and egg-derived Lysozyme (E1105).
5. **Soy (`SOY`)**: Covers *Glycine max*, Soy Protein Isolate/Concentrate, Soy Flour, Tofu, Edamame, Miso, Tempeh, Natto, and Soy-derived Lecithin (E322).
6. **Wheat (`WHEAT`)**: Covers all *Triticum* species (Common wheat, Durum, Spelt, Kamut, Emmer, Einkorn), Semolina, Farina, Seitan, and gluten proteins (Gliadins, Glutenins).
7. **Fish (`FISH`)**: Covers finned fish species (Cod, Salmon, Tuna, Anchovy, Mackerel) and derivatives such as Fish Sauce and Isinglass (collagen fining agent).
8. **Shellfish (`SHELLFISH`)**: Covers crustacean shellfish (Shrimp, Prawn, Crab, Lobster, Krill) and mollusks (Squid, Clam, Mussel, Oyster) driven by muscle tropomyosin.
9. **Sesame (`SESAME`)**: Covers *Sesamum indicum*, Tahini, Halva, Sesame Flour, and unrefined Gingelly/Sesame oil (US FASTER Act 2023).
10. **Sulfites (`SULFITE`)**: Covers Sulfur Dioxide and inorganic salts (E220 to E228, Sodium/Potassium Metabisulfite). Regulated above $10\text{ mg/kg}$ ($10\text{ ppm}$) due to acute bronchospasms in asthmatics.

### 4.2. Handling Hidden & Multi-Allergen Derivatives
* **Lecithin (`E322` / `e322_lecithin`)**:
  * Industry reality: Lecithin can be derived from Soy, Egg, Sunflower, or Rapeseed.
  * When a label simply prints `"Emulsifier (322)"` or `"Lecithin"`, FoodLence creates a dual-link in `kb.ingredient_allergens`:
    * `SOY` $\rightarrow$ `certainty = 'probable'` (FDA cited)
    * `EGG` $\rightarrow$ `certainty = 'possible'` (EFSA cited)
  * Result: If a child allergic to soy or egg scans the product, the engine deterministically generates a `caution` warning.
* **Lysozyme (`E1105` / `e1105_lysozyme`)**:
  * Extracted from egg whites, used as an antimicrobial in cheese and wine.
  * Explicitly mapped to `EGG` $\rightarrow$ `certainty = 'definite'`.
* **Sodium / Calcium Caseinate**:
  * Frequently used as non-dairy whiteners or meat binders.
  * Explicitly mapped to `MILK` $\rightarrow$ `certainty = 'definite'`.
* **Sri Lankan Market Nuances**:
  * Curated local aliases include: `"Maida"` and `"Atta"` for Wheat Flour; `"Gingelly Oil"` for Sesame Oil; `"Badam"` for Almond; `"Kaju"` for Cashew; `"Belacan"` for Shrimp Paste; and `"Pol Kiri"` (Coconut Milk, safe neutral).

---

## 5. Stored Translation Query Layer & Inter-Module API Contracts

Member 3's query layer encapsulates complex SQL operations within high-performance PostgreSQL stored functions.

### 5.1. Backend API Contract (Developer D — Dilshan)

#### 1. Entity Translation Function: `kb.fn_resolve_ingredients()`
When Developer B's ML model predicts standardized ingredient slugs, Developer D's FastAPI backend executes:
```sql
SELECT * FROM kb.fn_resolve_ingredients(ARRAY['whey', 'e322_lecithin', 'cane_sugar']);
```
**JSON Output Payload**:
```json
[
  {
    "slug": "whey",
    "canonical_name": "Whey",
    "ingredient_type": "allergen_source",
    "explanation": "Liquid byproduct of cheese manufacturing containing globular milk proteins.",
    "allergens": [
      {"code": "MILK", "name": "Milk", "certainty": "definite", "source": "FDA"}
    ],
    "e_number": null,
    "additive_category": null,
    "concern_level": null
  },
  {
    "slug": "e322_lecithin",
    "canonical_name": "Lecithin",
    "ingredient_type": "additive",
    "explanation": "Phospholipid mixture extracted primarily from soybeans or eggs.",
    "allergens": [
      {"code": "SOY", "name": "Soy", "certainty": "probable", "source": "FDA"},
      {"code": "EGG", "name": "Egg", "certainty": "possible", "source": "EFSA"}
    ],
    "e_number": "E322",
    "additive_category": "Emulsifier",
    "concern_level": 2
  }
]
```

#### 2. Multi-Profile Scan Evaluation: `app.fn_evaluate_scan()` & `app.fn_scan_safety()`
Fulfills **FR-06** and **FR-08** (evaluating one scan across up to 5 family profiles without physical re-scanning):
```sql
-- Returns detailed per-ingredient findings for Profile X
SELECT * FROM app.fn_evaluate_scan(:scan_id, :profile_id);

-- Returns overall aggregate rating: 'safe', 'caution', or 'unsafe'
SELECT app.fn_scan_safety(:scan_id, :profile_id);
```

**Deterministic Safety Decision Rules**:
* `unsafe` (Red): A `definite` allergen of the active profile is found in a declared ingredient.
* `caution` (Yellow): A `probable` or `possible` allergen is found, OR an allergen is found exclusively in a precautionary statement (`is_precautionary = true`), OR an additive flagged in `app.profile_additives` is detected.
* `safe` (Green): Zero profile allergens detected.
* *Unknown Fallback*: The API checks `app.fn_scan_unmatched_count(:scan_id)`. If unmatched fragments exist, the UI renders an advisory banner.

#### 3. Deterministic Fallback Matcher: `kb.fn_match_ingredient()`
If the cloud ML model is bypassed (manual search fallback, FR-01/FR-05):
```sql
SELECT * FROM kb.fn_match_ingredient('sodium caseinate', 0.45, 5);
```
Executes a 3-stage cascade:
* Stage 1: Exact canonical match (Score: 1.00)
* Stage 2: Curated alias match (Score: 0.98)
* Stage 3: Trigram similarity fuzzy match over GIN index (Score: 0.45 to 0.97)

### 5.2. Machine Learning Contract (Developer B — Rashmika)
* **Target Label Contract**: The ML model's categorical classification classes are strictly mapped to `kb.ingredients.slug`.
* **Slug Immutability**: Database trigger `trg_ingredients_slug_immutable` aborts any transaction attempting to modify an existing slug, ensuring ML model weights can never break in production.
* **Retraining Pipeline**: The database view `app.v_inference_logs` automatically surfaces real-world noisy OCR strings alongside model predictions and confidence scores for periodic model retraining.

### 5.3. Mobile UI Contract (Developer A — Mekala)
* Tri-color visual feedback:
  * `safe` $\rightarrow$ Green Banner
  * `caution` $\rightarrow$ Yellow Banner (renders plain-language explanation of additives or precautionary traces)
  * `unsafe` $\rightarrow$ Red Danger Alert (prominently identifies matching profile allergen)

---

## 6. Seed Dataset & Migration Operations

The project repository provides a complete, modular seed pipeline in `knowledge_base_seed/` strictly aligned with the schema in `app/db/01_schema_final.sql`:

```text
knowledge_base_seed/
├── seed_allergens.sql      # 10 allergen groups + 10 additive categories
├── seed_additives.sql      # 105 food additives with E-numbers, categories, and explanations
├── seed_ingredients.sql    # 220+ primary ingredients + curated synonyms and local aliases
├── seed_mappings.sql       # Relational mappings linking ingredients/additives to allergen groups
└── seed_embeddings.py      # Vector embedding generator for semantic matching
```

### 6.1. Executing Alembic Migrations on Neon PostgreSQL
Always execute migrations over the **Direct connection string** (port 5432, without `-pooler`). The FastAPI runtime should use the pooled connection string.

```bash
# 1. Set database connection string in terminal
# Windows PowerShell
$env:DATABASE_URL="postgresql://foodlence_user:password@ep-sample-pooler.neon.tech/foodlence_db?sslmode=require"

# Linux / macOS
export DATABASE_URL="postgresql://foodlence_user:password@ep-sample-pooler.neon.tech/foodlence_db?sslmode=require"

# 2. Run Alembic migrations to apply schema
python -m alembic -c app/db/alembic.ini upgrade head
```

### 6.2. Executing Seed Pipeline via psql
Run the seed scripts in dependency order:
```bash
# 1. Allergen Groups & Categories
psql "$DATABASE_URL" -f knowledge_base_seed/seed_allergens.sql

# 2. Additives & E-numbers (105 entities)
psql "$DATABASE_URL" -f knowledge_base_seed/seed_additives.sql

# 3. Ingredients & Synonyms (220+ entities)
psql "$DATABASE_URL" -f knowledge_base_seed/seed_ingredients.sql

# 4. Allergen Semantic Mappings
psql "$DATABASE_URL" -f knowledge_base_seed/seed_mappings.sql
```

### 6.3. Running the Smoke Test & Verification Suite
Validate database integrity with `app/db/03_validation_and_smoke_test.sql`:
```bash
psql "$DATABASE_URL" -f app/db/03_validation_and_smoke_test.sql
```
* **Part A (Curation Linter)**: Asserts that no active allergen sources lack allergen mappings, no additives lack details, and all active ingredients have plain-language explanations.
* **Part B (Transactional Smoke Test)**: Executes 24+ assertions across triggers, 5-profile constraints, tenant isolation, and scan safety evaluations inside a transaction and **rolls back automatically** (`ROLLBACK`), leaving zero test debris.
* Expected Output: `NOTICE: FoodLence smoke test: ALL CHECKS PASSED`.

---

## 7. Viva Voce & Academic Defense Q&A Cheat Sheet

### Q1: Why did you alter the proposal's schema from JSONB arrays to normalized 3NF tables?
> *"The proposal's initial schema used JSONB arrays for profile allergens and ingredient aliases. In an allergy-detection system where missing an ingredient is life-threatening, JSONB arrays cannot enforce foreign key referential integrity. Transitioning to 3NF ensures no orphaned allergen IDs can exist. Furthermore, normalized rows in `kb.ingredient_aliases` allow us to attach PostgreSQL GIN Trigram indexes (`pg_trgm`), enabling lightning-fast fuzzy matching ($<5\text{ ms}$) on distorted OCR strings. This provides robust architectural rigor and prevents update anomalies."*

### Q2: How does the database handle ambiguous additives like E322 (Lecithin)?
> *"Lecithin can be derived from soybeans or eggs. Our relational mapping table `kb.ingredient_allergens` supports a many-to-many relationship with a `certainty` classification (`definite`, `probable`, `possible`). For E322, we map to both `SOY` (probable) and `EGG` (possible). When evaluated by `app.fn_evaluate_scan()`, if the active profile contains either allergy, the system flags the product with a `caution` safety warning and renders a plain-language explanation, completely eliminating false-negative risks."*

### Q3: How do you enforce tenant isolation across multi-profile family accounts?
> *"We enforce multi-tenant isolation at the database constraint level. In `app.profiles`, we define a composite unique constraint `(profile_id, user_id)`. In `app.scans`, the foreign key references `(profile_id, user_id)`. This guarantees at the database engine level that User A cannot evaluate or attach a scan to a profile belonging to User B, even if an API route was misconfigured."*

### Q4: How is the Medical Liability Disclaimer tracked in the database?
> *"In compliance with Proposal Sections 10.4 and 14.4, `app.users` enforces a non-nullable timestamp `disclaimer_accepted_at timestamptz NOT NULL DEFAULT now()`. A user cannot complete registration without storing a verified cryptographic acknowledgment of the medical disclaimer."*

## 8. Source and Citation Appendix

The seed data is a manually curated dataset. It was not downloaded as one
single file from one provider. Each mapping records the applicable authority
(`FDA`, `EFSA`, or `CODEX`) in `kb.ingredient_allergens.source`; the source
authority is evidence of the regulatory basis used during curation, not a
claim that every row was copied verbatim from that authority.

| Dataset area | Primary reference | Use in FoodLence |
|---|---|---|
| Major food allergens | [FDA Food Allergies](https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies) | Defines the US major-allergen labeling context. |
| Allergen labeling guidance | [FDA Food Allergens/Gluten-Free Guidance](https://www.fda.gov/food/guidance-documents-regulatory-information-topic-food-and-dietary-supplements/food-allergensgluten-free-guidance-documents-regulatory-information) | Supports allergen declaration and ingredient interpretation. |
| Sesame as a major allergen | [FASTER Act information](https://www.foodsafety.gov/blog/food-allergy-safety-treatment-education-and-research-act-2021) | Supports the ninth US major allergen, sesame. |
| EU additive safety information | [EFSA Food Additives](https://www.efsa.europa.eu/en/topics/topic/food-additives) | Supports additive identity, E-number usage, and safety context. |
| EU additive authorization | [European Commission Food Additives Database](https://food.ec.europa.eu/food-safety/food-improvement-agents/additives/database_en) | Cross-checks authorized E-numbers, functions, and conditions of use. |
| International additive standard | [Codex GSFA Online](https://www.fao.org/fao-who-codexalimentarius/codex-texts/dbs/gsfa/en/) | Cross-checks international additive names and functional classes. |
| EU allergen terminology | [Regulation (EU) No 1169/2011](https://eur-lex.europa.eu/eli/reg/2011/1169/oj) | Supports EU food-information and allergen declaration terminology. |

**Access date:** 2026-10-28.

### 8.1. Seed Quality Audit

The repository seed files were checked on 2026-10-28 using deterministic
parsing of the SQL value rows:

| Check | Result |
|---|---:|
| Standard ingredient rows | 186 |
| Additive rows with E-numbers | 136 |
| Total unique seeded entities | 322 |
| Curated alias rows | 96 |
| Allergen-source ingredients | 150 |
| Allergen-source ingredients without mappings | 0 |
| Mapping rows with orphan ingredient slugs | 0 |
| Duplicate ingredient slugs | 0 |
| Duplicate additive slugs | 0 |
| Duplicate E-numbers | 0 |
| Empty ingredient/additive explanations | 0 |
| Empty mapping notes | 0 |

The audit confirms that the current files meet the documented minimum of
100 additives and 300 combined knowledge-base entities. It does not replace
the PostgreSQL validation script: run
`app/db/03_validation_and_smoke_test.sql` after loading the seeds to verify
database constraints, triggers, stored functions, and scan evaluation.

### 8.2. Curation Limitations

The current schema stores a source authority and a short note for each
allergen mapping, but it does not yet store a source URL, regulation section,
or per-row access date. For a future dataset revision, add a dedicated
curation-reference table or equivalent metadata so each mapping can be traced
to an exact citation. Until then, the table above is the authoritative
reference list for the current academic seed release.

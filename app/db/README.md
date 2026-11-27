# FoodLence Knowledge Base & Database Layer

**SE5104 Mini Project — Group 14**  
**Lead & Owner**: S.K.P.H. Deemantha (22CSE0348) — Knowledge Base Lead  
**Database Target**: PostgreSQL 15+ (Production: Managed Neon PG16)

---

## 1. Directory Structure

```text
app/db/
├── 01_schema_final.sql            # Master DDL script (schemas, types, tables, triggers, functions, views)
├── 02_seed_reference.sql         # Base seed (9 major FDA allergens + sulfites, additive categories, roles)
├── 03_validation_and_smoke_test.sql # Non-destructive verification suite & curation data quality checks
├── alembic.ini                    # Alembic migration configuration
├── alembic/                       # Alembic environment & version history
│   ├── env.py                     # Multi-schema configuration (kb, app, audit) + Neon env detection
│   ├── script.py.mako             # Revision template
│   └── versions/
│       ├── 0001_foundation.py     # Extensions, schemas, ENUMs, normalisation functions
│       ├── 0002_knowledge_base.py # Ingredients, aliases, additives, allergens, audit triggers, matchers
│       ├── 0003_application_identity.py # Roles, users, refresh tokens, profiles, profile constraints
│       ├── 0004_scans_and_matching.py   # Scans, ingredient fragments, matches, evaluation functions, v_inference_logs
│       └── 0005_seed_reference.py # Pre-seeded reference taxonomies
└── README.md                      # This documentation

knowledge_base_seed/               # Modular Seed Dataset (Proposal Deliverable: 300+ entities, 100+ additives)
├── seed_allergens.sql             # 9 major allergen groups + sulfite group + additive categories
├── seed_additives.sql             # 105 food additives with E-numbers, categories, and explanations
├── seed_ingredients.sql           # 220+ primary ingredients + curated synonyms and local aliases
├── seed_mappings.sql              # Relational mappings linking ingredients/additives to allergen groups
└── seed_embeddings.py             # Vector embedding extraction utility
```

> **Full Documentation**: See [KNOWLEDGE_BASE_GUIDE.md](../../KNOWLEDGE_BASE_GUIDE.md) for the complete scientific curation manual, regulatory taxonomies, and academic defense notes.

---

## 2. Schema Architecture & Design Justifications

The database is divided into three isolated schemas:
1. `kb` (**Knowledge Base**): Curated reference data (ingredients, chemical aliases, additives, allergen groups).
2. `app` (**Application Data**): User credentials, multi-profiles, scans, match results, and session tokens.
3. `audit` (**Audit Trail**): Append-only change log for knowledge base modifications.

### Key Architectural Decisions (Viva & Academic Defense)
- **3NF Normalisation over Proposal JSONB Arrays**:
  - `app.profile_allergens` and `kb.ingredient_aliases` are relational tables rather than JSONB arrays. This guarantees foreign key referential integrity, avoids orphaned IDs, and allows indexing with PostgreSQL Trigram GIN indexes (`pg_trgm`) for typo tolerance.
- **Additives as Subtypes of Ingredients**:
  - `kb.additive_details` is a 1:1 subtype table of `kb.ingredients`. Because the ML classifier predicts both ingredient names and E-numbers as entity slugs, a single root dictionary provides a unified lookup path while keeping additive-specific columns out of the main table.
- **Precautionary Allergen Distinction**:
  - `app.scan_ingredients.is_precautionary` isolates *"May contain traces of..."* statements so the system returns `caution` rather than `unsafe`, avoiding false positive panic while maintaining user safety.
- **Tenant Isolation & Security**:
  - Scans enforce composite foreign keys `(profile_id, user_id) REFERENCES app.profiles(profile_id, user_id)` ensuring User A can never attach or evaluate a scan against User B's profile.
  - User records enforce `disclaimer_accepted_at` (timestamptz) fulfilling the mandatory Medical Liability waiver (Proposal Section 10.4 & 14.4).
  - Refresh tokens are tracked in `app.refresh_tokens` for token rotation and instant revocation on logout (Proposal Section 7.6 & 10.3).

---

## 3. Alembic Migrations

### Prerequisites
```bash
pip install alembic sqlalchemy psycopg2-binary
```

### Direct vs Pooled Connection Note (Neon DB)
> **IMPORTANT**: Always run migrations over the **Direct connection string** (port 5432, without `-pooler`). The FastAPI runtime should use the pooled connection string.

### Environment Variable
Set `DATABASE_URL` in your `.env` or terminal:
```bash
# Windows PowerShell
$env:DATABASE_URL="postgresql://user:password@ep-sample-pooler.neon.tech/foodlence?sslmode=require"

# Linux / macOS
export DATABASE_URL="postgresql://user:password@ep-sample-pooler.neon.tech/foodlence?sslmode=require"
```

### Running Migrations
From the project root:
```bash
# Apply all migrations to the latest revision
python -m alembic -c app/db/alembic.ini upgrade head

# Rollback one revision
python -m alembic -c app/db/alembic.ini downgrade -1

# Rollback completely to base
python -m alembic -c app/db/alembic.ini downgrade base

# View migration history
python -m alembic -c app/db/alembic.ini history
```

---

## 4. Running the Smoke Test & Verification Suite

The file `app/db/03_validation_and_smoke_test.sql` serves two roles:
1. **Part A (Curation Linter)**: Read-only data quality checks (flags active ingredients missing plain-language descriptions, orphan allergen links, or missing aliases).
2. **Part B (Transactional Smoke Test)**: Executes functional assertions across the entire data lifecycle (matcher, triggers, multi-profiles, tenant isolation, scan safety evaluations) and **rolls back automatically** (`ROLLBACK`), leaving zero test garbage in the database.

### Running with psql:
```bash
psql "$DATABASE_URL" -f app/db/03_validation_and_smoke_test.sql
```
Expected output on success:
```text
NOTICE:  FoodLence smoke test: ALL CHECKS PASSED
```
Expected output on success:
```text
NOTICE:  FoodLence smoke test: ALL CHECKS PASSED
```

---

## 5. Team Integration Contracts

### ML Contract (with Developer B - Rashmika)
- Model target labels are mapped to `kb.ingredients.slug` (e.g., `whey`, `sodium_caseinate`, `e322`).
- The slug is protected by trigger `kb.fn_slug_immutable()` and cannot be mutated once created.
- Retraining export data is exposed via view `app.v_inference_logs`.

### Backend API Contract (with Developer D - Dilshan)
FastAPI queries two primary stored functions:
1. `kb.fn_resolve_ingredients(p_slugs text[])`: Resolves model-predicted slugs into allergen groups, additive descriptions, and plain-language warnings in a single call.
2. `app.fn_evaluate_scan(p_scan_id uuid, p_profile_id uuid)` and `app.fn_scan_safety(p_scan_id uuid, p_profile_id uuid)`: Evaluates a scan against any profile of the owner without requiring a physical re-scan (FR-08).

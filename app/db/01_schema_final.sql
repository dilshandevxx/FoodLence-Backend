-- =============================================================================
--  FoodLence — AI-Based Food Label Scanner
--  Knowledge base + application schema (PostgreSQL 15+, tested target: Neon PG16)
--  SE5104 Mini Project, Group 14 — Sabaragamuwa University of Sri Lanka
--  Owner: Heshan (S.K.P.H. Deemantha) — Knowledge Base Lead
--
--  Language scope : ENGLISH ONLY (no translation tables, no language columns)
--  Normal form    : 3NF (see NORMALISATION NOTES at the end)
--  Schemas        : kb (reference data) | app (users, profiles, scans) | audit
--
--  HOW TO USE WITH ALEMBIC
--    This file is split into migration blocks. Each block is marked
--    "MIGRATION 000N". Copy each block into db/sql/000N_*.sql and execute it from
--    the matching Alembic revision with op.execute(Path(...).read_text()).
--    Write a downgrade for every revision (DROP in reverse order).
--
--  NEON NOTES
--    * Run migrations over the DIRECT connection string, not the "-pooler" one.
--    * The FastAPI runtime should use the pooled connection string.
--    * Needs PostgreSQL 15+ (ON DELETE SET NULL (column_list) is used).
-- =============================================================================


-- #############################################################################
--  MIGRATION 0001 — FOUNDATION (extensions, schemas, enums, shared functions)
-- #############################################################################

CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- fuzzy matching of OCR typos
CREATE EXTENSION IF NOT EXISTS unaccent;    -- strip diacritics during normalisation
CREATE EXTENSION IF NOT EXISTS citext;      -- case-insensitive names and emails
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

CREATE SCHEMA IF NOT EXISTS kb;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS audit;

COMMENT ON SCHEMA kb    IS 'Curated reference data: ingredients, aliases, allergen groups, additives.';
COMMENT ON SCHEMA app   IS 'Transactional data: users, allergen profiles, scans and their match results.';
COMMENT ON SCHEMA audit IS 'Append-only change history for knowledge base tables.';


-- ---- Enumerated types -------------------------------------------------------

CREATE TYPE kb.ingredient_type AS ENUM (
    'allergen_source',   -- e.g. whey, peanut oil
    'additive',          -- e.g. tartrazine, lecithin
    'neutral'            -- e.g. water, salt, sugar
);

CREATE TYPE kb.allergen_certainty AS ENUM (
    'definite',          -- the term IS the allergen (whey -> milk)
    'probable',          -- usually derived from it (lecithin -> soy)
    'possible'           -- sometimes conceals it (natural flavouring)
);

CREATE TYPE kb.source_authority AS ENUM (
    'FDA', 'EFSA', 'CODEX', 'MANUFACTURER', 'TEAM_REVIEW'
);

CREATE TYPE app.severity_level AS ENUM ('mild', 'moderate', 'severe');

-- 'model' = predicted by Rashmika's classifier; the other three come from kb.fn_match_ingredient.
CREATE TYPE app.match_method AS ENUM ('model', 'exact', 'alias', 'fuzzy');

CREATE TYPE app.safety_result AS ENUM ('safe', 'caution', 'unsafe');

CREATE TYPE app.scan_status AS ENUM ('completed', 'failed');

-- 'manual_entry' covers the in-scope manual text-search fallback.
CREATE TYPE app.ocr_engine AS ENUM ('mlkit_ondevice', 'manual_entry');

CREATE TYPE app.platform AS ENUM ('android', 'ios');


-- ---- Text normalisation -----------------------------------------------------
--  Must be IMMUTABLE so it can be used in generated columns and indexes.
--  The one-argument unaccent(text) is only STABLE; the two-argument form with a
--  pinned dictionary can safely be wrapped as IMMUTABLE.

CREATE OR REPLACE FUNCTION kb.immutable_unaccent(p_text text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$
    SELECT public.unaccent('public.unaccent'::regdictionary, p_text);
$$;

CREATE OR REPLACE FUNCTION kb.normalise_text(p_text text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT NULLIF(
        btrim(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        lower(kb.immutable_unaccent(COALESCE(p_text, ''))),
                        '\(\s*\d+(\.\d+)?\s*%\s*\)|\d+(\.\d+)?\s*%', ' ', 'g'   -- strip "(12%)" / "12%"
                    ),
                    '[^a-z0-9 ]+', ' ', 'g'                                      -- strip punctuation
                ),
                '\s+', ' ', 'g'                                                  -- collapse whitespace
            )
        ),
    '');
$$;

COMMENT ON FUNCTION kb.normalise_text(text)
    IS 'Canonical normaliser: lowercase, de-accent, strip percentages and punctuation, collapse spaces. Used by generated columns AND by the matcher so they can never disagree.';

CREATE OR REPLACE FUNCTION public.fn_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


-- #############################################################################
--  MIGRATION 0002 — KNOWLEDGE BASE CORE (schema kb) + AUDIT
-- #############################################################################

-- ---- Allergen groups (9 major + sulfite group) ------------------------------
CREATE TABLE kb.allergen_groups (
    allergen_group_id smallint    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code              varchar(30) NOT NULL UNIQUE,            -- 'MILK', 'PEANUT', 'SULFITE'
    name              varchar(80) NOT NULL,                   -- display name, English
    description       text,
    is_major          boolean     NOT NULL DEFAULT true,      -- one of the 9 major groups
    icon_code         varchar(50) NOT NULL,
    display_order     smallint    NOT NULL DEFAULT 100,
    is_active         boolean     NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_allergen_code_format CHECK (code ~ '^[A-Z][A-Z_]*$')
);

COMMENT ON TABLE kb.allergen_groups
    IS 'The 9 major allergen groups (milk, egg, peanut, tree nut, soy, wheat, fish, shellfish, sesame) plus the sulfite group.';


-- ---- Additive categories ----------------------------------------------------
CREATE TABLE kb.additive_categories (
    additive_category_id smallserial PRIMARY KEY,
    code                 varchar(40) NOT NULL UNIQUE,
    name                 varchar(80) NOT NULL,
    description          text
);


-- ---- Ingredients (supertype) ------------------------------------------------
--  slug is the STABLE identifier shared with the ML team: the classifier's class
--  labels are slugs. It is immutable once created (trigger below).
CREATE TABLE kb.ingredients (
    ingredient_id   uuid               PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            varchar(80)        NOT NULL UNIQUE,
    canonical_name  citext             NOT NULL UNIQUE,
    normalised_name text               GENERATED ALWAYS AS (kb.normalise_text(canonical_name::text)) STORED,
    ingredient_type kb.ingredient_type NOT NULL,
    explanation     text,                                   -- plain-language explanation shown in the app
    is_active       boolean            NOT NULL DEFAULT true,
    created_at      timestamptz        NOT NULL DEFAULT now(),
    updated_at      timestamptz        NOT NULL DEFAULT now(),

    CONSTRAINT ck_ingredients_slug_format    CHECK (slug ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
    CONSTRAINT ck_ingredients_name_not_blank CHECK (btrim(canonical_name::text) <> ''),
    CONSTRAINT ck_ingredients_normalised_set CHECK (normalised_name IS NOT NULL),
    CONSTRAINT uq_ingredients_normalised     UNIQUE (normalised_name)
);

COMMENT ON COLUMN kb.ingredients.slug
    IS 'Stable machine identifier, e.g. sodium_caseinate. This is the ML class label. Never renamed.';


-- ---- Additive details (1:1 subtype) -----------------------------------------
CREATE TABLE kb.additive_details (
    ingredient_id        uuid        PRIMARY KEY
                                     REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
    e_number             varchar(15) UNIQUE,                 -- 'E322', 'E160a'
    additive_category_id smallint    NOT NULL
                                     REFERENCES kb.additive_categories(additive_category_id),
    concern_level        smallint    NOT NULL DEFAULT 1,     -- team-defined: 1 low .. 3 high

    CONSTRAINT ck_additive_concern CHECK (concern_level BETWEEN 1 AND 3),
    CONSTRAINT ck_additive_e_number_format CHECK (e_number IS NULL OR e_number ~ '^E[0-9]{3,4}[a-z]{0,3}$')
);

COMMENT ON COLUMN kb.additive_details.e_number
    IS 'Unique per additive. A generic code such as E322 belongs to the generic ingredient (lecithin_unspecified), not to soy_lecithin.';


-- ---- Ingredient -> allergen (many-to-many) ----------------------------------
CREATE TABLE kb.ingredient_allergens (
    ingredient_id     uuid                  NOT NULL
                                            REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
    allergen_group_id smallint              NOT NULL
                                            REFERENCES kb.allergen_groups(allergen_group_id) ON DELETE RESTRICT,
    certainty         kb.allergen_certainty NOT NULL DEFAULT 'definite',
    source            kb.source_authority   NOT NULL DEFAULT 'TEAM_REVIEW',
    note              text,                                  -- e.g. regulation or document reference
    created_at        timestamptz           NOT NULL DEFAULT now(),

    PRIMARY KEY (ingredient_id, allergen_group_id)
);

COMMENT ON TABLE kb.ingredient_allergens
    IS 'Many-to-many on purpose: lecithin may be soy- or sunflower-derived. A single FK would cause false negatives.';


-- ---- Aliases ----------------------------------------------------------------
CREATE TABLE kb.ingredient_aliases (
    alias_id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    ingredient_id    uuid        NOT NULL REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
    alias_text       citext      NOT NULL,
    normalised_alias text        GENERATED ALWAYS AS (kb.normalise_text(alias_text::text)) STORED,
    is_curated       boolean     NOT NULL DEFAULT true,
    is_active        boolean     NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_alias_normalised_set CHECK (normalised_alias IS NOT NULL)
);

-- An active alias resolves to exactly one ingredient, otherwise matching is ambiguous.
CREATE UNIQUE INDEX uq_alias_normalised ON kb.ingredient_aliases (normalised_alias) WHERE is_active;


-- ---- KB indexes -------------------------------------------------------------
CREATE INDEX ix_additive_details_category ON kb.additive_details (additive_category_id);
CREATE INDEX ix_ing_allergens_group       ON kb.ingredient_allergens (allergen_group_id);
CREATE INDEX ix_aliases_ingredient        ON kb.ingredient_aliases (ingredient_id);
CREATE INDEX ix_ingredients_type_active   ON kb.ingredients (ingredient_type) WHERE is_active;

-- Trigram indexes: make "emulsifer" match "emulsifier" without a full scan.
CREATE INDEX ix_ingredients_name_trgm ON kb.ingredients        USING gin (normalised_name  gin_trgm_ops);
CREATE INDEX ix_aliases_trgm          ON kb.ingredient_aliases USING gin (normalised_alias gin_trgm_ops);


-- ---- KB integrity triggers --------------------------------------------------

-- The slug is the ML contract: it can never change.
CREATE OR REPLACE FUNCTION kb.fn_slug_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.slug IS DISTINCT FROM OLD.slug THEN
        RAISE EXCEPTION 'kb.ingredients.slug is immutable (it is the ML class label); create a new ingredient instead.';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_ingredients_slug_immutable
    BEFORE UPDATE OF slug ON kb.ingredients
    FOR EACH ROW EXECUTE FUNCTION kb.fn_slug_immutable();

-- An alias must not equal another ingredient's canonical name (ambiguity -> wrong allergen).
CREATE OR REPLACE FUNCTION kb.fn_alias_no_canonical_clash()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_norm text := kb.normalise_text(NEW.alias_text::text);
BEGIN
    IF EXISTS (
        SELECT 1 FROM kb.ingredients i
         WHERE i.normalised_name = v_norm
           AND i.ingredient_id <> NEW.ingredient_id
    ) THEN
        RAISE EXCEPTION 'Alias "%" clashes with the canonical name of another ingredient.', NEW.alias_text;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_alias_no_canonical_clash
    BEFORE INSERT OR UPDATE OF alias_text ON kb.ingredient_aliases
    FOR EACH ROW EXECUTE FUNCTION kb.fn_alias_no_canonical_clash();

-- Reverse direction: a new canonical name must not equal another ingredient's active alias.
CREATE OR REPLACE FUNCTION kb.fn_canonical_no_alias_clash()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_norm text := kb.normalise_text(NEW.canonical_name::text);
BEGIN
    IF EXISTS (
        SELECT 1 FROM kb.ingredient_aliases a
         WHERE a.normalised_alias = v_norm
           AND a.is_active
           AND a.ingredient_id <> NEW.ingredient_id
    ) THEN
        RAISE EXCEPTION 'Canonical name "%" clashes with an alias of another ingredient.', NEW.canonical_name;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_canonical_no_alias_clash
    BEFORE INSERT OR UPDATE OF canonical_name ON kb.ingredients
    FOR EACH ROW EXECUTE FUNCTION kb.fn_canonical_no_alias_clash();

-- Only ingredients of type 'additive' may have an additive_details row.
CREATE OR REPLACE FUNCTION kb.fn_additive_requires_additive_type()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM kb.ingredients i
         WHERE i.ingredient_id = NEW.ingredient_id
           AND i.ingredient_type = 'additive'
    ) THEN
        RAISE EXCEPTION 'additive_details requires an ingredient with ingredient_type = ''additive''.';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_additive_requires_type
    BEFORE INSERT OR UPDATE OF ingredient_id ON kb.additive_details
    FOR EACH ROW EXECUTE FUNCTION kb.fn_additive_requires_additive_type();

-- The E-number is automatically an alias, so the two can never drift apart.
CREATE OR REPLACE FUNCTION kb.fn_sync_e_number_alias()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.e_number IS NOT NULL
       AND OLD.e_number IS DISTINCT FROM NEW.e_number THEN
        UPDATE kb.ingredient_aliases
           SET is_active = false
         WHERE ingredient_id = OLD.ingredient_id
           AND normalised_alias = kb.normalise_text(OLD.e_number);
    END IF;

    IF NEW.e_number IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM kb.ingredient_aliases a
         WHERE a.ingredient_id = NEW.ingredient_id
           AND a.normalised_alias = kb.normalise_text(NEW.e_number)
           AND a.is_active
    ) THEN
        INSERT INTO kb.ingredient_aliases (ingredient_id, alias_text)
        VALUES (NEW.ingredient_id, NEW.e_number);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_additive_e_number_alias
    AFTER INSERT OR UPDATE OF e_number ON kb.additive_details
    FOR EACH ROW EXECUTE FUNCTION kb.fn_sync_e_number_alias();

-- updated_at maintenance
CREATE TRIGGER trg_allergen_groups_updated BEFORE UPDATE ON kb.allergen_groups
    FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();
CREATE TRIGGER trg_ingredients_updated BEFORE UPDATE ON kb.ingredients
    FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();


-- ---- Audit trail for KB changes ---------------------------------------------
--  Set the actor per session before curating:  SET app.actor = 'heshan';
CREATE TABLE audit.kb_change_log (
    log_id     bigserial   PRIMARY KEY,
    table_name text        NOT NULL,
    record_id  text        NOT NULL,
    operation  char(1)     NOT NULL,
    old_data   jsonb,
    new_data   jsonb,
    changed_by text        NOT NULL DEFAULT COALESCE(NULLIF(current_setting('app.actor', true), ''), current_user),
    changed_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_audit_operation CHECK (operation IN ('I', 'U', 'D'))
);

CREATE INDEX ix_audit_changed_at_brin ON audit.kb_change_log USING brin (changed_at);

--  Generic: TG_ARGV[0] names the column that identifies the record.
CREATE OR REPLACE FUNCTION audit.fn_log_kb_change()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_old jsonb;
    v_new jsonb;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN v_old := to_jsonb(OLD); END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN v_new := to_jsonb(NEW); END IF;

    INSERT INTO audit.kb_change_log (table_name, record_id, operation, old_data, new_data)
    VALUES (
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
        COALESCE(v_new, v_old) ->> TG_ARGV[0],
        CASE TG_OP WHEN 'INSERT' THEN 'I' WHEN 'UPDATE' THEN 'U' ELSE 'D' END,
        v_old,
        v_new
    );
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_audit_allergen_groups
    AFTER INSERT OR UPDATE OR DELETE ON kb.allergen_groups
    FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('allergen_group_id');
CREATE TRIGGER trg_audit_ingredients
    AFTER INSERT OR UPDATE OR DELETE ON kb.ingredients
    FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('ingredient_id');
CREATE TRIGGER trg_audit_ingredient_allergens
    AFTER INSERT OR UPDATE OR DELETE ON kb.ingredient_allergens
    FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('ingredient_id');
CREATE TRIGGER trg_audit_additive_details
    AFTER INSERT OR UPDATE OR DELETE ON kb.additive_details
    FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('ingredient_id');
CREATE TRIGGER trg_audit_ingredient_aliases
    AFTER INSERT OR UPDATE OR DELETE ON kb.ingredient_aliases
    FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('alias_id');


-- ---- KB functions -----------------------------------------------------------

--  Deterministic safety-net matcher (runs independently of the ML model).
--    Stage 1  exact canonical name      score 1.00
--    Stage 2  curated alias (incl. E-numbers)   score 0.98
--    Stage 3  trigram fuzzy match (OCR typos)   score = similarity
--  Each stage runs only if the previous one found nothing.
--  Note: pg_trgm's % operator uses the session similarity_threshold (default 0.3);
--  keep p_fuzzy_threshold >= 0.3.
CREATE OR REPLACE FUNCTION kb.fn_match_ingredient(
    p_raw_text         text,
    p_fuzzy_threshold  real    DEFAULT 0.45,
    p_max_results      integer DEFAULT 5
)
RETURNS TABLE (
    ingredient_id  uuid,
    slug           text,
    canonical_name text,
    match_method   app.match_method,
    match_score    real
)
LANGUAGE plpgsql
STABLE
AS $$
#variable_conflict use_column
DECLARE
    v_norm text := kb.normalise_text(p_raw_text);
BEGIN
    IF v_norm IS NULL THEN
        RETURN;
    END IF;

    -- Stage 1: exact canonical name
    RETURN QUERY
        SELECT i.ingredient_id, i.slug::text, i.canonical_name::text,
               'exact'::app.match_method, 1.0::real
          FROM kb.ingredients i
         WHERE i.normalised_name = v_norm
           AND i.is_active
         LIMIT p_max_results;
    IF FOUND THEN RETURN; END IF;

    -- Stage 2: curated alias
    RETURN QUERY
        SELECT i.ingredient_id, i.slug::text, i.canonical_name::text,
               'alias'::app.match_method, 0.98::real
          FROM kb.ingredient_aliases a
          JOIN kb.ingredients i ON i.ingredient_id = a.ingredient_id
         WHERE a.normalised_alias = v_norm
           AND a.is_active
           AND i.is_active
         LIMIT p_max_results;
    IF FOUND THEN RETURN; END IF;

    -- Stage 3: trigram fuzzy match over canonical names AND aliases
    RETURN QUERY
        SELECT m.ingredient_id, m.slug, m.canonical_name,
               'fuzzy'::app.match_method, m.score
          FROM (
                SELECT DISTINCT ON (c.ingredient_id)
                       c.ingredient_id, c.slug, c.canonical_name, c.score
                  FROM (
                        SELECT i.ingredient_id, i.slug::text AS slug, i.canonical_name::text AS canonical_name,
                               similarity(i.normalised_name, v_norm)::real AS score
                          FROM kb.ingredients i
                         WHERE i.is_active
                           AND i.normalised_name % v_norm
                           AND similarity(i.normalised_name, v_norm) >= p_fuzzy_threshold
                        UNION ALL
                        SELECT i.ingredient_id, i.slug::text, i.canonical_name::text,
                               similarity(a.normalised_alias, v_norm)::real
                          FROM kb.ingredient_aliases a
                          JOIN kb.ingredients i ON i.ingredient_id = a.ingredient_id
                         WHERE a.is_active
                           AND i.is_active
                           AND a.normalised_alias % v_norm
                           AND similarity(a.normalised_alias, v_norm) >= p_fuzzy_threshold
                       ) c
                 ORDER BY c.ingredient_id, c.score DESC
               ) m
         ORDER BY m.score DESC
         LIMIT p_max_results;
END;
$$;

--  Translation query layer: model labels (slugs) -> allergens, additive info, explanation.
--  This is the function Dilshan's API calls after Rashmika's model predicts slugs.
CREATE OR REPLACE FUNCTION kb.fn_resolve_ingredients(p_slugs text[])
RETURNS TABLE (
    ingredient_id     uuid,
    slug              text,
    canonical_name    text,
    ingredient_type   kb.ingredient_type,
    explanation       text,
    allergens         jsonb,
    e_number          text,
    additive_category text,
    concern_level     smallint
)
LANGUAGE sql
STABLE
AS $$
    SELECT i.ingredient_id,
           i.slug::text,
           i.canonical_name::text,
           i.ingredient_type,
           i.explanation,
           COALESCE((
               SELECT jsonb_agg(
                          jsonb_build_object(
                              'code',      ag.code,
                              'name',      ag.name,
                              'certainty', ia.certainty,
                              'source',    ia.source)
                          ORDER BY ag.display_order)
                 FROM kb.ingredient_allergens ia
                 JOIN kb.allergen_groups ag ON ag.allergen_group_id = ia.allergen_group_id
                WHERE ia.ingredient_id = i.ingredient_id
           ), '[]'::jsonb),
           ad.e_number::text,
           ac.name::text,
           ad.concern_level
      FROM kb.ingredients i
      LEFT JOIN kb.additive_details    ad ON ad.ingredient_id = i.ingredient_id
      LEFT JOIN kb.additive_categories ac ON ac.additive_category_id = ad.additive_category_id
     WHERE i.slug = ANY (p_slugs)
       AND i.is_active;
$$;


-- #############################################################################
--  MIGRATION 0003 — APPLICATION IDENTITY (users, roles, profiles)
-- #############################################################################

CREATE TABLE app.roles (
    role_id smallserial PRIMARY KEY,
    code    varchar(30) NOT NULL UNIQUE,
    name    varchar(60) NOT NULL
);

CREATE TABLE app.users (
    user_id                uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    email                  citext       NOT NULL UNIQUE,
    password_hash          varchar(255) NOT NULL,                 -- bcrypt hash only, never plaintext
    display_name           varchar(150) NOT NULL,
    disclaimer_accepted_at timestamptz  NOT NULL DEFAULT now(),   -- Medical liability acknowledgement (Proposal Sec 10.4 & 14.4)
    email_verified_at      timestamptz,
    is_active              boolean      NOT NULL DEFAULT true,
    created_at             timestamptz  NOT NULL DEFAULT now(),
    updated_at             timestamptz  NOT NULL DEFAULT now(),

    CONSTRAINT ck_users_email_format CHECK (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$')
);

CREATE TABLE app.user_roles (
    user_id    uuid        NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    role_id    smallint    NOT NULL REFERENCES app.roles(role_id) ON DELETE RESTRICT,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX ix_user_roles_role ON app.user_roles (role_id);

-- ---- Refresh Tokens (JWT session management, revocation on logout) ----------
CREATE TABLE app.refresh_tokens (
    token_id     uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid         NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    token_hash   varchar(255) NOT NULL UNIQUE,
    device_name  varchar(100),
    expires_at   timestamptz  NOT NULL,
    revoked_at   timestamptz,
    created_at   timestamptz  NOT NULL DEFAULT now()
);

COMMENT ON TABLE app.refresh_tokens
    IS 'Tracks issued JWT refresh tokens to support secure revocation on logout and token rotation (Proposal Sec 7.6 & 10.3).';

CREATE INDEX ix_refresh_tokens_user ON app.refresh_tokens (user_id);
CREATE INDEX ix_refresh_tokens_hash ON app.refresh_tokens (token_hash) WHERE revoked_at IS NULL;

-- ---- Profiles (up to five per user, FR-08) ----------------------------------
CREATE TABLE app.profiles (
    profile_id   uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid         NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    profile_name varchar(100) NOT NULL,
    is_default   boolean      NOT NULL DEFAULT false,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    updated_at   timestamptz  NOT NULL DEFAULT now(),

    CONSTRAINT uq_profile_name_per_user UNIQUE (user_id, profile_name),
    -- Lets other tables prove "this profile belongs to this user" with a composite FK.
    CONSTRAINT uq_profile_owner UNIQUE (profile_id, user_id)
);

-- Exactly one default profile per user, enforced declaratively.
CREATE UNIQUE INDEX uq_one_default_profile_per_user ON app.profiles (user_id) WHERE is_default;

CREATE TABLE app.profile_allergens (
    profile_id        uuid               NOT NULL REFERENCES app.profiles(profile_id) ON DELETE CASCADE,
    allergen_group_id smallint           NOT NULL REFERENCES kb.allergen_groups(allergen_group_id) ON DELETE RESTRICT,
    severity          app.severity_level NOT NULL DEFAULT 'moderate',
    created_at        timestamptz        NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, allergen_group_id)
);

-- Additives a (health-conscious) user chooses to avoid even without an allergy.
CREATE TABLE app.profile_additives (
    profile_id    uuid        NOT NULL REFERENCES app.profiles(profile_id) ON DELETE CASCADE,
    ingredient_id uuid        NOT NULL REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, ingredient_id)
);

CREATE INDEX ix_profile_allergens_group      ON app.profile_allergens (allergen_group_id);
CREATE INDEX ix_profile_additives_ingredient ON app.profile_additives (ingredient_id);

-- Maximum five profiles per user. The user row is locked so two concurrent
-- inserts cannot both slip past the limit.
CREATE OR REPLACE FUNCTION app.fn_limit_profiles_per_user()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM app.users WHERE user_id = NEW.user_id FOR UPDATE;
    IF (SELECT count(*) FROM app.profiles WHERE user_id = NEW.user_id) >= 5 THEN
        RAISE EXCEPTION 'A user may have at most 5 profiles.' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_profiles_max_five
    BEFORE INSERT ON app.profiles
    FOR EACH ROW EXECUTE FUNCTION app.fn_limit_profiles_per_user();

-- "Make this the default" works without the client clearing the old default first.
CREATE OR REPLACE FUNCTION app.fn_demote_previous_default()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE app.profiles
       SET is_default = false
     WHERE user_id    = NEW.user_id
       AND profile_id <> NEW.profile_id
       AND is_default;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_profile_single_default
    BEFORE INSERT OR UPDATE OF is_default ON app.profiles
    FOR EACH ROW WHEN (NEW.is_default)
    EXECUTE FUNCTION app.fn_demote_previous_default();

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON app.users
    FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();
CREATE TRIGGER trg_profiles_updated BEFORE UPDATE ON app.profiles
    FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();


-- #############################################################################
--  MIGRATION 0004 — SCAN LOGS (inference history + ML feedback loop)
-- #############################################################################

--  app.scans + scan_ingredients + scan_matches are the normalised form of the
--  proposal's Inference_Logs table (see view app.v_inference_logs below).
--  Only OCR TEXT is stored — images never leave the device (privacy by design).
CREATE TABLE app.scans (
    scan_id           uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid             NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    profile_id        uuid,
    product_name      varchar(150),                                      -- user label or detected package title (FR-09)
    raw_ocr_text      text             NOT NULL,                         -- the noisy string from ML Kit
    ocr_engine        app.ocr_engine   NOT NULL DEFAULT 'mlkit_ondevice',
    ocr_confidence    numeric(5,2),                                      -- NULL when the OCR plugin gives none
    model_confidence  real,                                              -- classifier confidence, 0..1
    ml_model_version  varchar(40),
    safety_result     app.safety_result,                                 -- result for the profile used at scan time
    is_low_confidence boolean          NOT NULL DEFAULT false,           -- set by the API using the agreed threshold
    device_platform   app.platform,
    processing_ms     integer,
    status            app.scan_status  NOT NULL DEFAULT 'completed',
    scanned_at        timestamptz      NOT NULL DEFAULT now(),

    -- A scan can only reference a profile owned by the same user (tenant isolation).
    -- ON DELETE SET NULL (profile_id) keeps the user_id intact (PostgreSQL 15+).
    CONSTRAINT fk_scan_profile_owner
        FOREIGN KEY (profile_id, user_id)
        REFERENCES app.profiles (profile_id, user_id)
        ON DELETE SET NULL (profile_id),

    CONSTRAINT ck_scan_ocr_confidence   CHECK (ocr_confidence   IS NULL OR ocr_confidence   BETWEEN 0 AND 100),
    CONSTRAINT ck_scan_model_confidence CHECK (model_confidence IS NULL OR model_confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_scan_processing_ms    CHECK (processing_ms    IS NULL OR processing_ms >= 0),
    CONSTRAINT ck_scan_completed_has_result CHECK (status <> 'completed' OR safety_result IS NOT NULL)
);

-- Parsed ingredient fragments of one scan; self-reference models nesting:
--   "chocolate (sugar, cocoa mass, emulsifier (soy lecithin))"
CREATE TABLE app.scan_ingredients (
    scan_ingredient_id uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id            uuid         NOT NULL REFERENCES app.scans(scan_id) ON DELETE CASCADE,
    parent_id          uuid         REFERENCES app.scan_ingredients(scan_ingredient_id) ON DELETE CASCADE,
    position_index     smallint     NOT NULL,
    nesting_depth      smallint     NOT NULL DEFAULT 0,
    detected_text      varchar(300) NOT NULL,
    normalised_text    text         GENERATED ALWAYS AS (kb.normalise_text(detected_text)) STORED,
    is_precautionary   boolean      NOT NULL DEFAULT false,   -- from a "may contain traces of" statement

    CONSTRAINT uq_scan_ingredient_position UNIQUE (scan_id, position_index),
    CONSTRAINT ck_nesting_depth CHECK (nesting_depth BETWEEN 0 AND 5)
);

COMMENT ON COLUMN app.scan_ingredients.is_precautionary
    IS 'Precautionary labelling ("may contain traces of") is legally distinct from a declared ingredient and is reported as caution, not unsafe.';

-- What each fragment resolved to: zero, one or several KB entries.
CREATE TABLE app.scan_matches (
    match_id           uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_ingredient_id uuid             NOT NULL REFERENCES app.scan_ingredients(scan_ingredient_id) ON DELETE CASCADE,
    ingredient_id      uuid             NOT NULL REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
    match_method       app.match_method NOT NULL,
    match_score        real             NOT NULL,
    created_at         timestamptz      NOT NULL DEFAULT now(),

    CONSTRAINT uq_scan_match UNIQUE (scan_ingredient_id, ingredient_id),
    CONSTRAINT ck_match_score CHECK (match_score BETWEEN 0 AND 1)
);

-- History screen (FR-09): newest first, per user. (FK lookups on scan_ingredients.scan_id
-- and scan_matches.scan_ingredient_id are already served by the UNIQUE constraints.)
CREATE INDEX ix_scans_user_recent ON app.scans (user_id, scanned_at DESC);
CREATE INDEX ix_scans_profile     ON app.scans (profile_id) WHERE profile_id IS NOT NULL;
CREATE INDEX ix_scan_ingredients_parent ON app.scan_ingredients (parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX ix_scan_matches_ingredient ON app.scan_matches (ingredient_id);


-- ---- Safety evaluation (works for ANY of the user's profiles, no re-scan) ----
--
--  Rules:
--    unsafe  : a DEFINITE allergen of the profile found in a DECLARED ingredient
--    caution : probable/possible allergen, OR any profile allergen found only in a
--              precautionary ("may contain") statement, OR an additive the profile avoids
--    safe    : none of the above
--
--  IMPORTANT: "safe" means "no match found". Unmatched fragments are NOT safe;
--  the API must also check app.fn_scan_unmatched_count() and the low-confidence flag.
--
--  The profile must belong to the scan's owner; otherwise the function returns no rows
--  (tenant isolation, NFR-04).

CREATE OR REPLACE FUNCTION app.fn_evaluate_scan(p_scan_id uuid, p_profile_id uuid)
RETURNS TABLE (
    scan_ingredient_id uuid,
    detected_text      text,
    ingredient_id      uuid,
    slug               text,
    canonical_name     text,
    allergen_code      text,
    certainty          kb.allergen_certainty,
    is_precautionary   boolean,
    finding            app.safety_result
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT si.scan_ingredient_id, si.detected_text, si.is_precautionary
          FROM app.scan_ingredients si
          JOIN app.scans    s ON s.scan_id = si.scan_id
          JOIN app.profiles p ON p.profile_id = p_profile_id
                             AND p.user_id    = s.user_id
         WHERE si.scan_id = p_scan_id
    )
    SELECT sc.scan_ingredient_id,
           sc.detected_text::text,
           i.ingredient_id,
           i.slug::text,
           i.canonical_name::text,
           ag.code::text,
           ia.certainty,
           sc.is_precautionary,
           CASE WHEN ia.certainty = 'definite' AND NOT sc.is_precautionary
                THEN 'unsafe'::app.safety_result
                ELSE 'caution'::app.safety_result
           END
      FROM scoped sc
      JOIN app.scan_matches          sm ON sm.scan_ingredient_id = sc.scan_ingredient_id
      JOIN kb.ingredients             i ON i.ingredient_id       = sm.ingredient_id
      JOIN kb.ingredient_allergens   ia ON ia.ingredient_id      = i.ingredient_id
      JOIN kb.allergen_groups        ag ON ag.allergen_group_id  = ia.allergen_group_id
      JOIN app.profile_allergens     pa ON pa.allergen_group_id  = ia.allergen_group_id
                                       AND pa.profile_id         = p_profile_id
    UNION ALL
    SELECT sc.scan_ingredient_id,
           sc.detected_text::text,
           i.ingredient_id,
           i.slug::text,
           i.canonical_name::text,
           NULL::text,
           NULL::kb.allergen_certainty,
           sc.is_precautionary,
           'caution'::app.safety_result
      FROM scoped sc
      JOIN app.scan_matches      sm  ON sm.scan_ingredient_id = sc.scan_ingredient_id
      JOIN kb.ingredients        i   ON i.ingredient_id       = sm.ingredient_id
      JOIN app.profile_additives pad ON pad.ingredient_id     = i.ingredient_id
                                    AND pad.profile_id        = p_profile_id;
$$;

CREATE OR REPLACE FUNCTION app.fn_scan_safety(p_scan_id uuid, p_profile_id uuid)
RETURNS app.safety_result
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
               WHEN bool_or(f.finding = 'unsafe')  THEN 'unsafe'::app.safety_result
               WHEN bool_or(f.finding = 'caution') THEN 'caution'::app.safety_result
               ELSE 'safe'::app.safety_result
           END
      FROM app.fn_evaluate_scan(p_scan_id, p_profile_id) f;
$$;

-- Fragments that matched nothing: the API must treat these as "unknown", never "safe".
CREATE OR REPLACE FUNCTION app.fn_scan_unmatched_count(p_scan_id uuid)
RETURNS integer
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)::integer
      FROM app.scan_ingredients si
     WHERE si.scan_id = p_scan_id
       AND NOT EXISTS (
           SELECT 1 FROM app.scan_matches sm
            WHERE sm.scan_ingredient_id = si.scan_ingredient_id
       );
$$;

-- ---- View mirroring the proposal's Inference_Logs table ---------------------
--  Feeds Rashmika's retraining export (raw noisy text + what the system predicted).
--  Retention note: raw_ocr_text is user-linked; anonymise (drop user_id) before sharing a dataset.
CREATE VIEW app.v_inference_logs AS
SELECT s.scan_id          AS log_id,
       s.user_id,
       s.product_name,
       s.scanned_at       AS scan_timestamp,
       s.raw_ocr_text,
       COALESCE((
           SELECT jsonb_agg(
                      jsonb_build_object(
                          'slug',   i.slug,
                          'method', sm.match_method,
                          'score',  sm.match_score)
                      ORDER BY si.position_index)
             FROM app.scan_ingredients si
             JOIN app.scan_matches     sm ON sm.scan_ingredient_id = si.scan_ingredient_id
             JOIN kb.ingredients        i ON i.ingredient_id       = sm.ingredient_id
            WHERE si.scan_id = s.scan_id
       ), '[]'::jsonb)    AS predicted_entities,
       s.model_confidence AS confidence_score,
       s.safety_result
  FROM app.scans s;


-- =============================================================================
--  NORMALISATION NOTES (for the report / viva)
--
--  1NF  Every column is atomic. Allergens are rows in kb.ingredient_allergens and
--       profile_allergens, not comma lists or arrays. A scan's ingredient list is
--       decomposed into app.scan_ingredients rows.
--
--  2NF  Composite keys (ingredient_id, allergen_group_id) and (profile_id,
--       allergen_group_id): every non-key column (certainty, source, severity)
--       depends on the whole key.
--
--  3NF  No transitive dependencies:
--       * category name/description live in kb.additive_categories;
--       * allergen display name/description live in kb.allergen_groups;
--       * role name lives in app.roles;
--       * additive-only attributes live in the 1:1 subtype kb.additive_details,
--         so kb.ingredients has no mostly-NULL columns.
--
--  Deliberate design decisions (justify in the viva):
--       * Profiles use a junction table (profile_allergens) instead of the proposal's
--         JSONB array: referential integrity, indexable, and joinable in SQL.
--       * "Additives" are a subtype of ingredients, because an E-number is also a
--         label the ML model can predict; one entity table keeps one lookup path.
--       * normalised_name / normalised_alias / normalised_text are STORED GENERATED
--         columns: derived, but computed by the database, so they cannot drift.
--       * Inference_Logs is stored in normalised form (scans, scan_ingredients,
--         scan_matches) and exposed through app.v_inference_logs.
-- =============================================================================

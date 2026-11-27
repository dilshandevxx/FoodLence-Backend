"""Knowledge base core (schema kb) and audit trail

Revision ID: 0002_knowledge_base
Revises: 0001_foundation
Create Date: 2026-10-11 12:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_knowledge_base'
down_revision: Union[str, Sequence[str], None] = '0001_foundation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Allergen Groups
    op.execute("""
    CREATE TABLE kb.allergen_groups (
        allergen_group_id smallint    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        code              varchar(30) NOT NULL UNIQUE,
        name              varchar(80) NOT NULL,
        description       text,
        is_major          boolean     NOT NULL DEFAULT true,
        icon_code         varchar(50) NOT NULL,
        display_order     smallint    NOT NULL DEFAULT 100,
        is_active         boolean     NOT NULL DEFAULT true,
        created_at        timestamptz NOT NULL DEFAULT now(),
        updated_at        timestamptz NOT NULL DEFAULT now(),

        CONSTRAINT ck_allergen_code_format CHECK (code ~ '^[A-Z][A-Z_]*$')
    );
    """)

    # 2. Additive Categories
    op.execute("""
    CREATE TABLE kb.additive_categories (
        additive_category_id smallserial PRIMARY KEY,
        code                 varchar(40) NOT NULL UNIQUE,
        name                 varchar(80) NOT NULL,
        description          text
    );
    """)

    # 3. Ingredients (Supertype)
    op.execute("""
    CREATE TABLE kb.ingredients (
        ingredient_id   uuid               PRIMARY KEY DEFAULT gen_random_uuid(),
        slug            varchar(80)        NOT NULL UNIQUE,
        canonical_name  citext             NOT NULL UNIQUE,
        normalised_name text               GENERATED ALWAYS AS (kb.normalise_text(canonical_name::text)) STORED,
        ingredient_type kb.ingredient_type NOT NULL,
        explanation     text,
        is_active       boolean            NOT NULL DEFAULT true,
        created_at      timestamptz        NOT NULL DEFAULT now(),
        updated_at      timestamptz        NOT NULL DEFAULT now(),

        CONSTRAINT ck_ingredients_slug_format    CHECK (slug ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
        CONSTRAINT ck_ingredients_name_not_blank CHECK (btrim(canonical_name::text) <> ''),
        CONSTRAINT ck_ingredients_normalised_set CHECK (normalised_name IS NOT NULL),
        CONSTRAINT uq_ingredients_normalised     UNIQUE (normalised_name)
    );
    """)

    # 4. Additive Details (1:1 Subtype)
    op.execute("""
    CREATE TABLE kb.additive_details (
        ingredient_id        uuid        PRIMARY KEY
                                         REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
        e_number             varchar(15) UNIQUE,
        additive_category_id smallint    NOT NULL
                                         REFERENCES kb.additive_categories(additive_category_id),
        concern_level        smallint    NOT NULL DEFAULT 1,

        CONSTRAINT ck_additive_concern CHECK (concern_level BETWEEN 1 AND 3),
        CONSTRAINT ck_additive_e_number_format CHECK (e_number IS NULL OR e_number ~ '^E[0-9]{3,4}[a-z]{0,3}$')
    );
    """)

    # 5. Ingredient -> Allergen (Many-to-Many)
    op.execute("""
    CREATE TABLE kb.ingredient_allergens (
        ingredient_id     uuid                  NOT NULL
                                                REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
        allergen_group_id smallint              NOT NULL
                                                REFERENCES kb.allergen_groups(allergen_group_id) ON DELETE RESTRICT,
        certainty         kb.allergen_certainty NOT NULL DEFAULT 'definite',
        source            kb.source_authority   NOT NULL DEFAULT 'TEAM_REVIEW',
        note              text,
        created_at        timestamptz           NOT NULL DEFAULT now(),

        PRIMARY KEY (ingredient_id, allergen_group_id)
    );
    """)

    # 6. Ingredient Aliases
    op.execute("""
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
    CREATE UNIQUE INDEX uq_alias_normalised ON kb.ingredient_aliases (normalised_alias) WHERE is_active;
    """)

    # 7. Indexes
    op.execute("CREATE INDEX ix_additive_details_category ON kb.additive_details (additive_category_id);")
    op.execute("CREATE INDEX ix_ing_allergens_group ON kb.ingredient_allergens (allergen_group_id);")
    op.execute("CREATE INDEX ix_aliases_ingredient ON kb.ingredient_aliases (ingredient_id);")
    op.execute("CREATE INDEX ix_ingredients_type_active ON kb.ingredients (ingredient_type) WHERE is_active;")
    op.execute("CREATE INDEX ix_ingredients_name_trgm ON kb.ingredients USING gin (normalised_name gin_trgm_ops);")
    op.execute("CREATE INDEX ix_aliases_trgm ON kb.ingredient_aliases USING gin (normalised_alias gin_trgm_ops);")

    # 8. KB Integrity Triggers
    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
    CREATE TRIGGER trg_allergen_groups_updated BEFORE UPDATE ON kb.allergen_groups
        FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();
    CREATE TRIGGER trg_ingredients_updated BEFORE UPDATE ON kb.ingredients
        FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();
    """)

    # 9. Audit Trail
    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("CREATE TRIGGER trg_audit_allergen_groups AFTER INSERT OR UPDATE OR DELETE ON kb.allergen_groups FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('allergen_group_id');")
    op.execute("CREATE TRIGGER trg_audit_ingredients AFTER INSERT OR UPDATE OR DELETE ON kb.ingredients FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('ingredient_id');")
    op.execute("CREATE TRIGGER trg_audit_ingredient_allergens AFTER INSERT OR UPDATE OR DELETE ON kb.ingredient_allergens FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('ingredient_id');")
    op.execute("CREATE TRIGGER trg_audit_additive_details AFTER INSERT OR UPDATE OR DELETE ON kb.additive_details FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('ingredient_id');")
    op.execute("CREATE TRIGGER trg_audit_ingredient_aliases AFTER INSERT OR UPDATE OR DELETE ON kb.ingredient_aliases FOR EACH ROW EXECUTE FUNCTION audit.fn_log_kb_change('alias_id');")

    # 10. KB Matcher & Resolver Functions
    op.execute("""
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
    """)

    op.execute("""
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
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS kb.fn_resolve_ingredients(text[]);")
    op.execute("DROP FUNCTION IF EXISTS kb.fn_match_ingredient(text, real, integer);")

    op.execute("DROP TRIGGER IF EXISTS trg_audit_ingredient_aliases ON kb.ingredient_aliases;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_additive_details ON kb.additive_details;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_ingredient_allergens ON kb.ingredient_allergens;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_ingredients ON kb.ingredients;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_allergen_groups ON kb.allergen_groups;")
    op.execute("DROP FUNCTION IF EXISTS audit.fn_log_kb_change();")
    op.execute("DROP TABLE IF EXISTS audit.kb_change_log CASCADE;")

    op.execute("DROP TRIGGER IF EXISTS trg_additive_e_number_alias ON kb.additive_details;")
    op.execute("DROP FUNCTION IF EXISTS kb.fn_sync_e_number_alias();")
    op.execute("DROP TRIGGER IF EXISTS trg_additive_requires_type ON kb.additive_details;")
    op.execute("DROP FUNCTION IF EXISTS kb.fn_additive_requires_additive_type();")
    op.execute("DROP TRIGGER IF EXISTS trg_canonical_no_alias_clash ON kb.ingredients;")
    op.execute("DROP FUNCTION IF EXISTS kb.fn_canonical_no_alias_clash();")
    op.execute("DROP TRIGGER IF EXISTS trg_alias_no_canonical_clash ON kb.ingredient_aliases;")
    op.execute("DROP FUNCTION IF EXISTS kb.fn_alias_no_canonical_clash();")
    op.execute("DROP TRIGGER IF EXISTS trg_ingredients_slug_immutable ON kb.ingredients;")
    op.execute("DROP FUNCTION IF EXISTS kb.fn_slug_immutable();")

    op.execute("DROP TABLE IF EXISTS kb.ingredient_aliases CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb.ingredient_allergens CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb.additive_details CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb.ingredients CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb.additive_categories CASCADE;")
    op.execute("DROP TABLE IF EXISTS kb.allergen_groups CASCADE;")

"""Foundation: extensions, schemas, enums, shared functions

Revision ID: 0001_foundation
Revises: None
Create Date: 2026-10-11 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_foundation'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # 2. Schemas
    op.execute("CREATE SCHEMA IF NOT EXISTS kb;")
    op.execute("CREATE SCHEMA IF NOT EXISTS app;")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit;")

    op.execute("COMMENT ON SCHEMA kb IS 'Curated reference data: ingredients, aliases, allergen groups, additives.';")
    op.execute("COMMENT ON SCHEMA app IS 'Transactional data: users, allergen profiles, scans and their match results.';")
    op.execute("COMMENT ON SCHEMA audit IS 'Append-only change history for knowledge base tables.';")

    # 3. Enumerated Types
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE kb.ingredient_type AS ENUM ('allergen_source', 'additive', 'neutral');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE kb.allergen_certainty AS ENUM ('definite', 'probable', 'possible');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE kb.source_authority AS ENUM ('FDA', 'EFSA', 'CODEX', 'MANUFACTURER', 'TEAM_REVIEW');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE app.severity_level AS ENUM ('mild', 'moderate', 'severe');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE app.match_method AS ENUM ('model', 'exact', 'alias', 'fuzzy');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE app.safety_result AS ENUM ('safe', 'caution', 'unsafe');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE app.scan_status AS ENUM ('completed', 'failed');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE app.ocr_engine AS ENUM ('mlkit_ondevice', 'manual_entry');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    op.execute("""
    DO $$ BEGIN
        CREATE TYPE app.platform AS ENUM ('android', 'ios');
    EXCEPTION WHEN duplicate_object THEN null; END $$;
    """)

    # 4. Text Normalisation & Maintenance Functions
    op.execute("""
    CREATE OR REPLACE FUNCTION kb.immutable_unaccent(p_text text)
    RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
    AS $$
        SELECT public.unaccent('public.unaccent'::regdictionary, p_text);
    $$;
    """)

    op.execute("""
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
                            '\\(\\s*\\d+(\\.\\d+)?\\s*%\\s*\\)|\\d+(\\.\\d+)?\\s*%', ' ', 'g'
                        ),
                        '[^a-z0-9 ]+', ' ', 'g'
                    ),
                    '\\s+', ' ', 'g'
                )
            ),
        '');
    $$;
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION public.fn_set_updated_at()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
        NEW.updated_at := now();
        RETURN NEW;
    END;
    $$;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.fn_set_updated_at();")
    op.execute("DROP FUNCTION IF EXISTS kb.normalise_text(text);")
    op.execute("DROP FUNCTION IF EXISTS kb.immutable_unaccent(text);")

    op.execute("DROP TYPE IF EXISTS app.platform;")
    op.execute("DROP TYPE IF EXISTS app.ocr_engine;")
    op.execute("DROP TYPE IF EXISTS app.scan_status;")
    op.execute("DROP TYPE IF EXISTS app.safety_result;")
    op.execute("DROP TYPE IF EXISTS app.match_method;")
    op.execute("DROP TYPE IF EXISTS app.severity_level;")
    op.execute("DROP TYPE IF EXISTS kb.source_authority;")
    op.execute("DROP TYPE IF EXISTS kb.allergen_certainty;")
    op.execute("DROP TYPE IF EXISTS kb.ingredient_type;")

    op.execute("DROP SCHEMA IF EXISTS audit CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS kb CASCADE;")

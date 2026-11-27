"""Application identity: roles, users, refresh tokens, profiles

Revision ID: 0003_application_identity
Revises: 0002_knowledge_base
Create Date: 2026-10-11 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_application_identity'
down_revision: Union[str, Sequence[str], None] = '0002_knowledge_base'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Roles
    op.execute("""
    CREATE TABLE app.roles (
        role_id smallserial PRIMARY KEY,
        code    varchar(30) NOT NULL UNIQUE,
        name    varchar(60) NOT NULL
    );
    """)

    # 2. Users
    op.execute("""
    CREATE TABLE app.users (
        user_id                uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
        email                  citext       NOT NULL UNIQUE,
        password_hash          varchar(255) NOT NULL,
        display_name           varchar(150) NOT NULL,
        disclaimer_accepted_at timestamptz  NOT NULL DEFAULT now(),
        email_verified_at      timestamptz,
        is_active              boolean      NOT NULL DEFAULT true,
        created_at             timestamptz  NOT NULL DEFAULT now(),
        updated_at             timestamptz  NOT NULL DEFAULT now(),

        CONSTRAINT ck_users_email_format CHECK (email ~* '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$')
    );
    """)

    # 3. User Roles
    op.execute("""
    CREATE TABLE app.user_roles (
        user_id    uuid        NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
        role_id    smallint    NOT NULL REFERENCES app.roles(role_id) ON DELETE RESTRICT,
        granted_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, role_id)
    );
    CREATE INDEX ix_user_roles_role ON app.user_roles (role_id);
    """)

    # 4. Refresh Tokens (JWT session management & revocation)
    op.execute("""
    CREATE TABLE app.refresh_tokens (
        token_id     uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id      uuid         NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
        token_hash   varchar(255) NOT NULL UNIQUE,
        device_name  varchar(100),
        expires_at   timestamptz  NOT NULL,
        revoked_at   timestamptz,
        created_at   timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_refresh_tokens_user ON app.refresh_tokens (user_id);
    CREATE INDEX ix_refresh_tokens_hash ON app.refresh_tokens (token_hash) WHERE revoked_at IS NULL;
    """)

    # 5. Profiles (FR-08: up to 5 profiles per user)
    op.execute("""
    CREATE TABLE app.profiles (
        profile_id   uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id      uuid         NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
        profile_name varchar(100) NOT NULL,
        is_default   boolean      NOT NULL DEFAULT false,
        created_at   timestamptz  NOT NULL DEFAULT now(),
        updated_at   timestamptz  NOT NULL DEFAULT now(),

        CONSTRAINT uq_profile_name_per_user UNIQUE (user_id, profile_name),
        CONSTRAINT uq_profile_owner UNIQUE (profile_id, user_id)
    );
    CREATE UNIQUE INDEX uq_one_default_profile_per_user ON app.profiles (user_id) WHERE is_default;
    """)

    # 6. Profile Allergens (3NF)
    op.execute("""
    CREATE TABLE app.profile_allergens (
        profile_id        uuid               NOT NULL REFERENCES app.profiles(profile_id) ON DELETE CASCADE,
        allergen_group_id smallint           NOT NULL REFERENCES kb.allergen_groups(allergen_group_id) ON DELETE RESTRICT,
        severity          app.severity_level NOT NULL DEFAULT 'moderate',
        created_at        timestamptz        NOT NULL DEFAULT now(),
        PRIMARY KEY (profile_id, allergen_group_id)
    );
    CREATE INDEX ix_profile_allergens_group ON app.profile_allergens (allergen_group_id);
    """)

    # 7. Profile Additives (Avoided by health-conscious users)
    op.execute("""
    CREATE TABLE app.profile_additives (
        profile_id    uuid        NOT NULL REFERENCES app.profiles(profile_id) ON DELETE CASCADE,
        ingredient_id uuid        NOT NULL REFERENCES kb.ingredients(ingredient_id) ON DELETE CASCADE,
        created_at    timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (profile_id, ingredient_id)
    );
    CREATE INDEX ix_profile_additives_ingredient ON app.profile_additives (ingredient_id);
    """)

    # 8. Profile Business Rule Triggers
    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
    CREATE TRIGGER trg_users_updated BEFORE UPDATE ON app.users
        FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();
    CREATE TRIGGER trg_profiles_updated BEFORE UPDATE ON app.profiles
        FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_profiles_updated ON app.profiles;")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated ON app.users;")
    op.execute("DROP TRIGGER IF EXISTS trg_profile_single_default ON app.profiles;")
    op.execute("DROP FUNCTION IF EXISTS app.fn_demote_previous_default();")
    op.execute("DROP TRIGGER IF EXISTS trg_profiles_max_five ON app.profiles;")
    op.execute("DROP FUNCTION IF EXISTS app.fn_limit_profiles_per_user();")

    op.execute("DROP TABLE IF EXISTS app.profile_additives CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.profile_allergens CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.profiles CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.refresh_tokens CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.user_roles CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.users CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.roles CASCADE;")

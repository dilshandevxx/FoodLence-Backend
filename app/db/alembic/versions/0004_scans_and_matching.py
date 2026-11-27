"""Scan logs, ingredient parsing, matches, evaluation functions and inference logs view

Revision ID: 0004_scans_and_matching
Revises: 0003_application_identity
Create Date: 2026-10-11 12:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0004_scans_and_matching'
down_revision: Union[str, Sequence[str], None] = '0003_application_identity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Scans Table
    op.execute("""
    CREATE TABLE app.scans (
        scan_id           uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id           uuid             NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
        profile_id        uuid,
        product_name      varchar(150),
        raw_ocr_text      text             NOT NULL,
        ocr_engine        app.ocr_engine   NOT NULL DEFAULT 'mlkit_ondevice',
        ocr_confidence    numeric(5,2),
        model_confidence  real,
        ml_model_version  varchar(40),
        safety_result     app.safety_result,
        is_low_confidence boolean          NOT NULL DEFAULT false,
        device_platform   app.platform,
        processing_ms     integer,
        status            app.scan_status  NOT NULL DEFAULT 'completed',
        scanned_at        timestamptz      NOT NULL DEFAULT now(),

        CONSTRAINT fk_scan_profile_owner
            FOREIGN KEY (profile_id, user_id)
            REFERENCES app.profiles (profile_id, user_id)
            ON DELETE SET NULL (profile_id),

        CONSTRAINT ck_scan_ocr_confidence   CHECK (ocr_confidence   IS NULL OR ocr_confidence   BETWEEN 0 AND 100),
        CONSTRAINT ck_scan_model_confidence CHECK (model_confidence IS NULL OR model_confidence BETWEEN 0 AND 1),
        CONSTRAINT ck_scan_processing_ms    CHECK (processing_ms    IS NULL OR processing_ms >= 0),
        CONSTRAINT ck_scan_completed_has_result CHECK (status <> 'completed' OR safety_result IS NOT NULL)
    );
    """)

    # 2. Parsed Ingredient Fragments (hierarchical nesting)
    op.execute("""
    CREATE TABLE app.scan_ingredients (
        scan_ingredient_id uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
        scan_id            uuid         NOT NULL REFERENCES app.scans(scan_id) ON DELETE CASCADE,
        parent_id          uuid         REFERENCES app.scan_ingredients(scan_ingredient_id) ON DELETE CASCADE,
        position_index     smallint     NOT NULL,
        nesting_depth      smallint     NOT NULL DEFAULT 0,
        detected_text      varchar(300) NOT NULL,
        normalised_text    text         GENERATED ALWAYS AS (kb.normalise_text(detected_text)) STORED,
        is_precautionary   boolean      NOT NULL DEFAULT false,

        CONSTRAINT uq_scan_ingredient_position UNIQUE (scan_id, position_index),
        CONSTRAINT ck_nesting_depth CHECK (nesting_depth BETWEEN 0 AND 5)
    );
    """)

    # 3. Scan Fragment Matches
    op.execute("""
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
    """)

    # 4. Indexes
    op.execute("CREATE INDEX ix_scans_user_recent ON app.scans (user_id, scanned_at DESC);")
    op.execute("CREATE INDEX ix_scans_profile ON app.scans (profile_id) WHERE profile_id IS NOT NULL;")
    op.execute("CREATE INDEX ix_scan_ingredients_parent ON app.scan_ingredients (parent_id) WHERE parent_id IS NOT NULL;")
    op.execute("CREATE INDEX ix_scan_matches_ingredient ON app.scan_matches (ingredient_id);")

    # 5. Safety Evaluation Functions
    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    # 6. ML Retraining Feedback View (Proposal Inference_Logs Contract)
    op.execute("""
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
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS app.v_inference_logs;")
    op.execute("DROP FUNCTION IF EXISTS app.fn_scan_unmatched_count(uuid);")
    op.execute("DROP FUNCTION IF EXISTS app.fn_scan_safety(uuid, uuid);")
    op.execute("DROP FUNCTION IF EXISTS app.fn_evaluate_scan(uuid, uuid);")

    op.execute("DROP TABLE IF EXISTS app.scan_matches CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.scan_ingredients CASCADE;")
    op.execute("DROP TABLE IF EXISTS app.scans CASCADE;")

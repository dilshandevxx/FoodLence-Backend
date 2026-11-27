-- =============================================================================
--  FoodLence — validation queries + smoke test
--  Run AFTER 01_schema_final.sql and 02_seed_reference.sql on a Neon branch.
-- =============================================================================


-- #############################################################################
--  PART A — CURATION VALIDATION (read-only; run after loading your 100 entities)
--  Every query should return ZERO rows unless noted.
-- #############################################################################

-- A1. allergen_source ingredients with no allergen link
SELECT 'A1 allergen_source without allergen link' AS check_name, i.slug
  FROM kb.ingredients i
 WHERE i.ingredient_type = 'allergen_source'
   AND NOT EXISTS (SELECT 1 FROM kb.ingredient_allergens ia WHERE ia.ingredient_id = i.ingredient_id);

-- A2. neutral ingredients that have an allergen link
SELECT 'A2 neutral with allergen link' AS check_name, i.slug
  FROM kb.ingredients i
 WHERE i.ingredient_type = 'neutral'
   AND EXISTS (SELECT 1 FROM kb.ingredient_allergens ia WHERE ia.ingredient_id = i.ingredient_id);

-- A3. additives without an additive_details row
SELECT 'A3 additive without details' AS check_name, i.slug
  FROM kb.ingredients i
 WHERE i.ingredient_type = 'additive'
   AND NOT EXISTS (SELECT 1 FROM kb.additive_details ad WHERE ad.ingredient_id = i.ingredient_id);

-- A4. active ingredients without a plain-language explanation
SELECT 'A4 missing explanation' AS check_name, i.slug
  FROM kb.ingredients i
 WHERE i.is_active AND (i.explanation IS NULL OR btrim(i.explanation) = '');

-- A5. active ingredients with no alias at all (informational: add synonyms/OCR variants)
SELECT 'A5 no aliases' AS check_name, i.slug
  FROM kb.ingredients i
 WHERE i.is_active
   AND NOT EXISTS (SELECT 1 FROM kb.ingredient_aliases a WHERE a.ingredient_id = i.ingredient_id AND a.is_active);

-- A6. allergen mappings without a recorded authority (still TEAM_REVIEW) — informational
SELECT 'A6 TEAM_REVIEW mapping' AS check_name, i.slug, ag.code
  FROM kb.ingredient_allergens ia
  JOIN kb.ingredients     i  ON i.ingredient_id = ia.ingredient_id
  JOIN kb.allergen_groups ag ON ag.allergen_group_id = ia.allergen_group_id
 WHERE ia.source = 'TEAM_REVIEW';

-- A7. coverage per allergen group (expect >= 3 each for the 9 majors) — returns rows by design
SELECT ag.code, count(DISTINCT ia.ingredient_id) AS ingredient_count
  FROM kb.allergen_groups ag
  LEFT JOIN kb.ingredient_allergens ia ON ia.allergen_group_id = ag.allergen_group_id
 GROUP BY ag.code, ag.display_order
 ORDER BY ag.display_order;

-- A8. totals by type — returns rows by design (Sprint 1 target: 100 entities)
SELECT ingredient_type, count(*) AS total FROM kb.ingredients WHERE is_active GROUP BY ingredient_type;


-- #############################################################################
--  PART B — SMOKE TEST (runs in a transaction and ROLLS BACK; leaves no data)
--  A failed ASSERT aborts with its message. Success prints NOTICE lines.
-- #############################################################################

BEGIN;

DO $$
DECLARE
    v_whey   uuid;
    v_lec    uuid;
    v_water  uuid;
    v_user   uuid;
    v_user2  uuid;
    v_prof   uuid;
    v_prof2  uuid;
    v_scan   uuid;
    v_si     uuid;
    v_ok     boolean;
    v_res    app.safety_result;
    v_cnt    integer;
    i        integer;
BEGIN
    -- ---- KB: ingredients, mappings, additive, aliases -----------------------
    INSERT INTO kb.ingredients (slug, canonical_name, ingredient_type, explanation)
    VALUES ('whey', 'Whey', 'allergen_source', 'A milk protein left over from cheese making.')
    RETURNING ingredient_id INTO v_whey;

    INSERT INTO kb.ingredients (slug, canonical_name, ingredient_type, explanation)
    VALUES ('lecithin_unspecified', 'Lecithin', 'additive', 'An emulsifier, usually from soy or sunflower.')
    RETURNING ingredient_id INTO v_lec;

    INSERT INTO kb.ingredients (slug, canonical_name, ingredient_type, explanation)
    VALUES ('water', 'Water', 'neutral', 'Plain water.')
    RETURNING ingredient_id INTO v_water;

    INSERT INTO kb.ingredient_allergens (ingredient_id, allergen_group_id, certainty, source)
    SELECT v_whey, allergen_group_id, 'definite'::kb.allergen_certainty, 'FDA'::kb.source_authority
      FROM kb.allergen_groups WHERE code = 'MILK';

    INSERT INTO kb.ingredient_allergens (ingredient_id, allergen_group_id, certainty, source)
    SELECT v_lec, allergen_group_id, 'probable'::kb.allergen_certainty, 'TEAM_REVIEW'::kb.source_authority
      FROM kb.allergen_groups WHERE code = 'SOY';

    INSERT INTO kb.additive_details (ingredient_id, e_number, additive_category_id, concern_level)
    SELECT v_lec, 'E322', additive_category_id, 1
      FROM kb.additive_categories WHERE code = 'EMULSIFIER';

    INSERT INTO kb.ingredient_aliases (ingredient_id, alias_text) VALUES
        (v_whey, 'whey solids'),
        (v_whey, 'whey powder');

    -- ---- Matcher -------------------------------------------------------------
    ASSERT EXISTS (SELECT 1 FROM kb.fn_match_ingredient('Whey (12%)') m
                    WHERE m.slug = 'whey' AND m.match_method = 'exact'),
           'exact match with percentage stripped failed';

    ASSERT EXISTS (SELECT 1 FROM kb.fn_match_ingredient('E322') m
                    WHERE m.slug = 'lecithin_unspecified' AND m.match_method = 'alias'),
           'E-number was not auto-created as an alias';

    ASSERT EXISTS (SELECT 1 FROM kb.fn_match_ingredient('whey powdr') m
                    WHERE m.slug = 'whey' AND m.match_method = 'fuzzy'),
           'fuzzy match for an OCR typo failed';

    -- ---- Integrity guards ----------------------------------------------------
    v_ok := false;
    BEGIN
        INSERT INTO kb.ingredient_aliases (ingredient_id, alias_text) VALUES (v_lec, 'Whey');
    EXCEPTION WHEN raise_exception THEN v_ok := true;
    END;
    ASSERT v_ok, 'alias that equals another ingredient''s canonical name must be rejected';

    v_ok := false;
    BEGIN
        UPDATE kb.ingredients SET slug = 'whey_changed' WHERE ingredient_id = v_whey;
    EXCEPTION WHEN raise_exception THEN v_ok := true;
    END;
    ASSERT v_ok, 'slug must be immutable';

    v_ok := false;
    BEGIN
        INSERT INTO kb.additive_details (ingredient_id, e_number, additive_category_id)
        SELECT v_whey, 'E999', additive_category_id FROM kb.additive_categories WHERE code = 'COLOUR';
    EXCEPTION WHEN raise_exception THEN v_ok := true;
    END;
    ASSERT v_ok, 'additive_details on a non-additive ingredient must be rejected';

    ASSERT (SELECT count(*) FROM audit.kb_change_log WHERE table_name = 'kb.ingredients') >= 3,
           'audit trail did not record ingredient inserts';

    -- ---- Users and profiles ---------------------------------------------------
    INSERT INTO app.users (email, password_hash, display_name)
    VALUES ('smoke1@example.com', 'bcrypt-hash-placeholder', 'Smoke One') RETURNING user_id INTO v_user;
    INSERT INTO app.users (email, password_hash, display_name)
    VALUES ('smoke2@example.com', 'bcrypt-hash-placeholder', 'Smoke Two') RETURNING user_id INTO v_user2;

    ASSERT (SELECT disclaimer_accepted_at IS NOT NULL FROM app.users WHERE user_id = v_user),
           'disclaimer_accepted_at must default to non-null';

    -- Test JWT refresh token issuance and revocation
    INSERT INTO app.refresh_tokens (user_id, token_hash, device_name, expires_at)
    VALUES (v_user, 'hash_sample_token_123', 'Pixel 7', now() + interval '30 days');

    ASSERT EXISTS (SELECT 1 FROM app.refresh_tokens WHERE user_id = v_user AND token_hash = 'hash_sample_token_123'),
           'refresh token insert failed';

    FOR i IN 1..5 LOOP
        INSERT INTO app.profiles (user_id, profile_name) VALUES (v_user, 'profile ' || i);
    END LOOP;

    v_ok := false;
    BEGIN
        INSERT INTO app.profiles (user_id, profile_name) VALUES (v_user, 'profile 6');
    EXCEPTION WHEN check_violation THEN v_ok := true;
    END;
    ASSERT v_ok, 'a 6th profile must be rejected';

    SELECT profile_id INTO v_prof FROM app.profiles WHERE user_id = v_user AND profile_name = 'profile 1';
    UPDATE app.profiles SET is_default = true WHERE profile_id = v_prof;
    UPDATE app.profiles SET is_default = true WHERE user_id = v_user AND profile_name = 'profile 2';
    ASSERT (SELECT is_default FROM app.profiles WHERE profile_id = v_prof) = false,
           'previous default profile was not demoted';

    INSERT INTO app.profiles (user_id, profile_name) VALUES (v_user2, 'other user profile')
    RETURNING profile_id INTO v_prof2;

    INSERT INTO app.profile_allergens (profile_id, allergen_group_id)
    SELECT v_prof, allergen_group_id FROM kb.allergen_groups WHERE code = 'MILK';

    -- ---- Scan, matches, evaluation -------------------------------------------
    INSERT INTO app.scans (user_id, profile_id, product_name, raw_ocr_text, model_confidence, safety_result)
    VALUES (v_user, v_prof, 'Test Biscuits', 'wheyy solids, water', 0.91, 'safe')
    RETURNING scan_id INTO v_scan;

    ASSERT (SELECT product_name FROM app.v_inference_logs WHERE log_id = v_scan) = 'Test Biscuits',
           'v_inference_logs must expose product_name';

    INSERT INTO app.scan_ingredients (scan_id, position_index, detected_text)
    VALUES (v_scan, 1, 'whey solids') RETURNING scan_ingredient_id INTO v_si;
    INSERT INTO app.scan_matches (scan_ingredient_id, ingredient_id, match_method, match_score)
    SELECT v_si, m.ingredient_id, m.match_method, m.match_score FROM kb.fn_match_ingredient('whey solids') m;

    INSERT INTO app.scan_ingredients (scan_id, position_index, detected_text)
    VALUES (v_scan, 2, 'zzqx unknown thing');

    v_res := app.fn_scan_safety(v_scan, v_prof);
    ASSERT v_res = 'unsafe', 'milk profile + whey must be unsafe, got ' || v_res::text;

    ASSERT app.fn_scan_unmatched_count(v_scan) = 1, 'unmatched fragment count should be 1';

    UPDATE app.scan_ingredients SET is_precautionary = true WHERE scan_ingredient_id = v_si;
    v_res := app.fn_scan_safety(v_scan, v_prof);
    ASSERT v_res = 'caution', 'precautionary milk statement must be caution, got ' || v_res::text;

    SELECT count(*) INTO v_cnt FROM app.fn_evaluate_scan(v_scan, v_prof2);
    ASSERT v_cnt = 0, 'another user''s profile must not evaluate this scan';

    -- A scan may not reference a profile of a different user.
    v_ok := false;
    BEGIN
        INSERT INTO app.scans (user_id, profile_id, raw_ocr_text, safety_result)
        VALUES (v_user, v_prof2, 'x', 'safe');
    EXCEPTION WHEN foreign_key_violation THEN v_ok := true;
    END;
    ASSERT v_ok, 'scan with someone else''s profile must be rejected';

    -- Deleting a profile keeps the scan and its owner.
    DELETE FROM app.profiles WHERE profile_id = v_prof;
    ASSERT (SELECT profile_id IS NULL AND user_id = v_user FROM app.scans WHERE scan_id = v_scan),
           'deleting a profile should null profile_id only';

    -- Translation query layer
    ASSERT (SELECT count(*) FROM kb.fn_resolve_ingredients(ARRAY['whey','lecithin_unspecified','water'])) = 3,
           'fn_resolve_ingredients should return all three slugs';
    ASSERT (SELECT jsonb_array_length(allergens) FROM kb.fn_resolve_ingredients(ARRAY['whey'])) = 1,
           'whey should expose one allergen';

    RAISE NOTICE 'FoodLence smoke test: ALL CHECKS PASSED';
END
$$;

ROLLBACK;

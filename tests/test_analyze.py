import uuid
import pytest
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from app.models.profile import Profile
from app.models.user import User
from app.schemas.analyze import AnalyzeRequest
from app.api.v1.endpoints.analyze import analyze_food_label
from app.services.scan_service import scan_service


def test_analyze_endpoint_safe_product(db_session: Session):
    """
    Validates that food products without allergens or harmful additives return SAFE.
    """
    req = AnalyzeRequest(
        ocr_text="Ingredients: white rice, pure water, sunflower oil, sea salt.",
        has_ingredient_keywords=True,
    )
    res = analyze_food_label(request=req, background_tasks=BackgroundTasks(), db=db_session, current_user=None)

    assert res.status == "success"
    assert res.safety_verdict == "SAFE"
    assert res.verdict_color == "green"
    assert len(res.matched_allergens) == 0
    assert res.confidence_score > 0.6
    assert res.processing_time_ms < 3000.0  # Milestone: under 3.0s


def test_analyze_endpoint_allergen_detection(db_session: Session):
    """
    Validates accurate detection and extraction of multiple common food allergens.
    """
    req = AnalyzeRequest(
        ocr_text="Ingredients: enriched wheat flour, skimmed milk powder, pasteurized whole eggs, roasted peanuts, soy lecithin.",
        has_ingredient_keywords=True,
    )
    res = analyze_food_label(request=req, background_tasks=BackgroundTasks(), db=db_session, current_user=None)

    allergen_codes = {a.allergen_code for a in res.matched_allergens}
    assert "gluten" in allergen_codes or "wheat" in allergen_codes
    assert "milk" in allergen_codes
    assert "egg" in allergen_codes
    assert "peanut" in allergen_codes
    assert "soy" in allergen_codes


def test_analyze_endpoint_additive_extraction(db_session: Session):
    """
    Validates detection of E-numbers and chemical food additives.
    """
    req = AnalyzeRequest(
        ocr_text="Ingredients: carbonated water, sugar, acid (E330), color (E102, INS 110), preservative (E211).",
        has_ingredient_keywords=True,
    )
    res = analyze_food_label(request=req, background_tasks=BackgroundTasks(), db=db_session, current_user=None)

    e_numbers = {a.e_number for a in res.detected_additives}
    assert "E102" in e_numbers
    assert "E110" in e_numbers
    assert "E211" in e_numbers
    assert "E330" in e_numbers
    assert res.safety_verdict == "CAUTION"


def test_analyze_endpoint_profile_conflict_severe(db_session: Session):
    """
    Validates that when a detected allergen matches a severe allergy in user's profile,
    verdict is UNSAFE (red) with a direct danger warning.
    """
    user = User(
        id=uuid.uuid4(),
        email="dilshan_severe@foodlence.com",
        password_hash="fakehash",
        full_name="Dilshan Test",
    )
    profile = Profile(
        id=uuid.uuid4(),
        user_id=user.id,
        profile_name="Dilshan - Severe Allergies",
        is_primary=True,
        active_allergens=[
            {
                "allergen_id": "peanut",
                "name": "Peanuts",
                "severity": "severe",
            }
        ],
    )
    db_session.add(user)
    db_session.add(profile)
    db_session.commit()

    req = AnalyzeRequest(
        ocr_text="Ingredients: roasted peanuts, sea salt, palm oil.",
        profile_id=str(profile.id),
        has_ingredient_keywords=True,
    )
    res = analyze_food_label(request=req, background_tasks=BackgroundTasks(), db=db_session, current_user=user)

    assert res.safety_verdict == "UNSAFE"
    assert res.verdict_color == "red"
    assert "DANGER" in res.summary
    assert "Peanuts" in res.summary
    assert any(a.is_profile_conflict for a in res.matched_allergens)


def test_analyze_endpoint_latency_benchmark(db_session: Session):
    """
    Milestone 4 Benchmark: Verifies that end-to-end backend inference executes in under 3.0 seconds.
    """
    req = AnalyzeRequest(
        ocr_text="Ingredients: wheat flour, sugar, vegetable oil, cocoa powder, whey (milk), soy lecithin, sodium bicarbonate.",
        has_ingredient_keywords=True,
    )
    res = analyze_food_label(request=req, background_tasks=BackgroundTasks(), db=db_session, current_user=None)

    assert res.processing_time_ms < 3000.0

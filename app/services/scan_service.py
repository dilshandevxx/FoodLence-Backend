import time
import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.schemas.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    DetectedIngredient,
    MatchedAllergen,
    DetectedAdditive,
    ProfileEvaluationSummary,
)
from app.nlp.pipeline import nlp_pipeline
from app.nlp.confidence import confidence_scorer
from app.knowledge_base.allergen_engine import allergen_engine
from app.models.profile import Profile
from app.models.inference_log import InferenceLog
from app.models.user import User

logger = logging.getLogger(__name__)


class BackendScanService:
    """
    Core backend inference orchestration service.
    Coordinates NLP tokenization, allergen cross-referencing,
    profile conflict evaluation, and asynchronous telemetry logging.
    """

    @classmethod
    def execute_scan_analysis(
        cls,
        request: AnalyzeRequest,
        db: Optional[Session] = None,
        current_user: Optional[User] = None,
    ) -> AnalyzeResponse:
        start_time = time.perf_counter()

        # 1. Select the most salient text section for ingredient parsing
        text_to_analyze = (
            request.isolated_ingredients
            if (request.isolated_ingredients and len(request.isolated_ingredients.strip()) > 5)
            else request.ocr_text
        )

        # 2. NLP Entity Extraction
        ingredient_tokens, additive_codes = nlp_pipeline.process(text_to_analyze)

        # 3. Retrieve Active Dietary Profile Constraints
        profile_name = "Active Profile"
        profile_allergens = []
        profile_uuid: Optional[uuid.UUID] = None

        if request.profile_id and db is not None:
            try:
                p_id = uuid.UUID(request.profile_id)
                db_profile = db.query(Profile).filter(Profile.id == p_id).first()
                if db_profile:
                    profile_uuid = db_profile.id
                    profile_name = db_profile.profile_name
                    profile_allergens = db_profile.active_allergens or []
            except Exception as exc:
                logger.debug("Could not resolve profile %s: %s", request.profile_id, exc)

        # 4. Allergen & Additive Knowledge Base Matching
        raw_matched_allergens = allergen_engine.match_allergens_for_ingredients(ingredient_tokens, db=db)
        raw_detected_additives = allergen_engine.match_additives(additive_codes, db=db)

        # 5. Deterministic Verdict Evaluation
        verdict, color, summary, evaluated_allergens = allergen_engine.evaluate_safety_verdict(
            matched_allergens=raw_matched_allergens,
            detected_additives=raw_detected_additives,
            profile_allergens=profile_allergens,
            profile_name=profile_name,
        )

        # 6. Holistic Confidence Scoring
        confidence, requires_manual_check = confidence_scorer.evaluate(
            raw_text=request.raw_text or request.ocr_text,
            detected_ingredients=ingredient_tokens,
            has_keywords=request.has_ingredient_keywords or False,
        )

        # 7. Measure Latency
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Build schema components
        detected_ingredients_list = [
            DetectedIngredient(
                name=token,
                matched_standard=token.lower(),
                category="ingredient",
                confidence=0.90,
                is_additive=False,
            )
            for token in ingredient_tokens
        ]

        matched_allergens_list = [
            MatchedAllergen(
                allergen_code=item["allergen_code"],
                allergen_name=item["allergen_name"],
                severity_level=item["severity_level"],
                cross_reactivity=item["cross_reactivity"],
                matched_ingredient=item["matched_ingredient"],
                is_profile_conflict=item["is_profile_conflict"],
                notes=item.get("notes"),
            )
            for item in evaluated_allergens
        ]

        detected_additives_list = [
            DetectedAdditive(
                e_number=item["e_number"],
                name=item["name"],
                category=item["category"],
                risk_level=item["risk_level"],
                explanation=item.get("explanation"),
                health_concerns=item.get("health_concerns"),
            )
            for item in raw_detected_additives
        ]

        conflicts_count = sum(1 for a in matched_allergens_list if a.is_profile_conflict)

        profile_summary = ProfileEvaluationSummary(
            profile_id=str(profile_uuid) if profile_uuid else request.profile_id,
            profile_name=profile_name,
            active_allergens_count=len(profile_allergens),
            matched_conflicts_count=conflicts_count,
        )

        return AnalyzeResponse(
            status="success",
            safety_verdict=verdict,
            verdict_color=color,
            summary=summary,
            confidence_score=confidence,
            requires_manual_check=requires_manual_check,
            detected_ingredients=detected_ingredients_list,
            matched_allergens=matched_allergens_list,
            detected_additives=detected_additives_list,
            profile_evaluated=profile_summary,
            processing_time_ms=elapsed_ms,
        )

    @classmethod
    def log_inference_audit(
        cls,
        request: AnalyzeRequest,
        response: AnalyzeResponse,
        user_id: Optional[uuid.UUID] = None,
    ) -> None:
        """
        Background task to persist inference telemetry into Inference_Logs.
        Does not block client request response.
        """
        from app.db.session import SessionLocal

        try:
            with SessionLocal() as db:
                profile_uuid = None
                if request.profile_id:
                    try:
                        profile_uuid = uuid.UUID(request.profile_id)
                    except Exception:
                        pass

                log_entry = InferenceLog(
                    user_id=user_id,
                    profile_id=profile_uuid,
                    raw_ocr_text=request.ocr_text,
                    predicted_entities=[i.model_dump() for i in response.detected_ingredients],
                    matched_allergens=[a.model_dump() for a in response.matched_allergens],
                    detected_additives=[d.model_dump() for d in response.detected_additives],
                    confidence_score=response.confidence_score,
                    safety_result=response.safety_verdict,
                    requires_manual_check=response.requires_manual_check,
                    processing_time_ms=response.processing_time_ms,
                )
                db.add(log_entry)
                db.commit()
                logger.info("Inference log persisted successfully (ID: %s)", log_entry.id)
        except Exception as exc:
            logger.warning("Failed to persist inference log: %s", exc)


scan_service = BackendScanService()

import uuid
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.inference_log import InferenceLog
from app.models.profile import Profile


class HistoryService:
    @staticmethod
    def get_user_history(
        db: Session,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[int, List[dict]]:
        query = db.query(InferenceLog).filter(InferenceLog.user_id == user_id)
        total = query.count()

        offset = (page - 1) * page_size
        logs = query.order_by(InferenceLog.created_at.desc()).offset(offset).limit(page_size).all()

        results = []
        for log in logs:
            profile_name = None
            if log.profile:
                profile_name = log.profile.profile_name

            results.append({
                "id": log.id,
                "profile_id": log.profile_id,
                "profile_name": profile_name,
                "raw_ocr_text": log.raw_ocr_text,
                "safety_result": log.safety_result,
                "confidence_score": log.confidence_score,
                "requires_manual_check": log.requires_manual_check,
                "processing_time_ms": log.processing_time_ms,
                "created_at": log.created_at,
            })

        return total, results

    @staticmethod
    def get_history_detail(
        db: Session,
        log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[dict]:
        log = db.query(InferenceLog).filter(
            InferenceLog.id == log_id,
            InferenceLog.user_id == user_id,
        ).first()

        if not log:
            return None

        profile_name = log.profile.profile_name if log.profile else None

        return {
            "id": log.id,
            "profile_id": log.profile_id,
            "profile_name": profile_name,
            "raw_ocr_text": log.raw_ocr_text,
            "safety_result": log.safety_result,
            "confidence_score": log.confidence_score,
            "requires_manual_check": log.requires_manual_check,
            "processing_time_ms": log.processing_time_ms,
            "created_at": log.created_at,
            "predicted_entities": log.predicted_entities,
            "matched_allergens": log.matched_allergens,
            "detected_additives": log.detected_additives,
        }


history_service = HistoryService()

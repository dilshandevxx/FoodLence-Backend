from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session

from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.services.scan_service import scan_service
from app.api.v1.deps import get_db, get_current_user_optional
from app.models.user import User

router = APIRouter()


@router.post(
    "",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute AI/NLP Ingredient Extraction & Personalized Allergen Evaluation",
    description="""
    Primary inference endpoint for FoodLence mobile client.
    Accepts Edge OCR text payload and active profile ID, performs NLP entity tokenization,
    matches against allergen & additive taxonomies, and evaluates safety verdict under 3.0 seconds.
    Asynchronously persists inference audit trail into database.
    """,
)
def analyze_food_label(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> AnalyzeResponse:
    # 1. Execute core scan analysis and compute verdict
    response = scan_service.execute_scan_analysis(
        request=request,
        db=db,
        current_user=current_user,
    )

    # 2. Asynchronously persist audit telemetry in background
    user_id = current_user.id if current_user else None
    background_tasks.add_task(
        scan_service.log_inference_audit,
        request=request,
        response=response,
        user_id=user_id,
    )

    return response

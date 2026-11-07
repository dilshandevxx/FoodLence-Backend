import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.history import PaginatedHistoryResponse, ScanHistoryDetail
from app.services.history_service import history_service
from app.api.v1.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get paginated scan history for the current user",
)
def get_scan_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = history_service.get_user_history(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    return PaginatedHistoryResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.get(
    "/{history_id}",
    response_model=ScanHistoryDetail,
    status_code=status.HTTP_200_OK,
    summary="Get full details of a specific past scan inference",
)
def get_scan_detail(
    history_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = history_service.get_history_detail(
        db=db,
        log_id=history_id,
        user_id=current_user.id,
    )
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan record not found or access denied.",
        )
    return detail

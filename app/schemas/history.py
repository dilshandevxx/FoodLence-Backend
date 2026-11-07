import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ScanHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: Optional[uuid.UUID] = None
    profile_name: Optional[str] = None
    raw_ocr_text: str
    safety_result: str
    confidence_score: float
    requires_manual_check: bool
    processing_time_ms: Optional[float] = None
    created_at: datetime


class ScanHistoryDetail(ScanHistoryItem):
    predicted_entities: Optional[List[dict[str, Any]]] = None
    matched_allergens: Optional[List[dict[str, Any]]] = None
    detected_additives: Optional[List[dict[str, Any]]] = None


class PaginatedHistoryResponse(BaseModel):
    total: int = Field(..., description="Total count of scan records")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Items per page")
    items: List[ScanHistoryItem] = Field(default_factory=list)

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import String, Float, Boolean, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_ocr_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    predicted_entities: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=True,
    )
    matched_allergens: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=True,
    )
    detected_additives: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=True,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    safety_result: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    requires_manual_check: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    processing_time_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="inference_logs",
    )
    profile: Mapped["Profile | None"] = relationship(
        "Profile",
        back_populates="inference_logs",
    )

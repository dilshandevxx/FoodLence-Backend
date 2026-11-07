import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    standard_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    scientific_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    alternative_names: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    allergen_mappings: Mapped[list["IngredientAllergenMap"]] = relationship(
        "IngredientAllergenMap",
        back_populates="ingredient",
        cascade="all, delete-orphan",
    )
    embedding: Mapped["IngredientEmbedding | None"] = relationship(
        "IngredientEmbedding",
        back_populates="ingredient",
        uselist=False,
        cascade="all, delete-orphan",
    )

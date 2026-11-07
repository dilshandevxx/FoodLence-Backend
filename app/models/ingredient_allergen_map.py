import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class IngredientAllergenMap(Base):
    __tablename__ = "ingredient_allergen_mappings"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "allergen_id", name="uq_ingredient_allergen"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allergen_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("allergens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cross_reactivity_risk: Mapped[str] = mapped_column(
        String(50),
        default="direct",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    ingredient: Mapped["Ingredient"] = relationship(
        "Ingredient",
        back_populates="allergen_mappings",
    )
    allergen: Mapped["Allergen"] = relationship(
        "Allergen",
        back_populates="ingredient_mappings",
    )

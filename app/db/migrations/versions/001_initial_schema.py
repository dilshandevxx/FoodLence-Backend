"""initial schema with core tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-07 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users Table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. Profiles Table
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_name", sa.String(length=100), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active_allergens", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_profiles_user_id"), "profiles", ["user_id"], unique=False)

    # 3. Allergens Table
    op.create_table(
        "allergens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("allergen_code", sa.String(length=50), nullable=False),
        sa.Column("allergen_name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity_default", sa.String(length=50), nullable=False, server_default="high"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_allergens_allergen_code"), "allergens", ["allergen_code"], unique=True)

    # 4. Ingredients Table
    op.create_table(
        "ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("standard_name", sa.String(length=255), nullable=False),
        sa.Column("scientific_name", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("alternative_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_ingredients_standard_name"), "ingredients", ["standard_name"], unique=True)

    # 5. Ingredient Allergen Mappings Table
    op.create_table(
        "ingredient_allergen_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allergen_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("allergens.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cross_reactivity_risk", sa.String(length=50), nullable=False, server_default="direct"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ingredient_id", "allergen_id", name="uq_ingredient_allergen"),
    )
    op.create_index(op.f("ix_ingredient_allergen_mappings_ingredient_id"), "ingredient_allergen_mappings", ["ingredient_id"], unique=False)
    op.create_index(op.f("ix_ingredient_allergen_mappings_allergen_id"), "ingredient_allergen_mappings", ["allergen_id"], unique=False)

    # 6. Additives Table
    op.create_table(
        "additives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("e_number", sa.String(length=20), nullable=False),
        sa.Column("standard_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("alternative_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_level", sa.String(length=50), nullable=False, server_default="caution"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("health_concerns", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_additives_e_number"), "additives", ["e_number"], unique=True)

    # 7. Ingredient Embeddings Table
    op.create_table(
        "ingredient_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("embedding_vector", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False, server_default="spacy-en-core-web-sm"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_ingredient_embeddings_ingredient_id"), "ingredient_embeddings", ["ingredient_id"], unique=True)

    # 8. Inference Logs Table
    op.create_table(
        "inference_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_ocr_text", sa.Text(), nullable=False),
        sa.Column("predicted_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matched_allergens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detected_additives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("safety_result", sa.String(length=50), nullable=False),
        sa.Column("requires_manual_check", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processing_time_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_inference_logs_user_id"), "inference_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_inference_logs_profile_id"), "inference_logs", ["profile_id"], unique=False)


def downgrade() -> None:
    op.drop_table("inference_logs")
    op.drop_table("ingredient_embeddings")
    op.drop_table("additives")
    op.drop_table("ingredient_allergen_mappings")
    op.drop_table("ingredients")
    op.drop_table("allergens")
    op.drop_table("profiles")
    op.drop_table("users")

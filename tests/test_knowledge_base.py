import uuid
import pytest
from sqlalchemy.orm import Session
from app.models.allergen import Allergen
from app.models.ingredient import Ingredient
from app.models.ingredient_allergen_map import IngredientAllergenMap
from app.models.additive import Additive
from app.knowledge_base.allergen_engine import allergen_engine


def test_database_backed_allergen_lookup(db_session: Session):
    """
    Validates dynamic DB lookup when an ingredient is mapped to an allergen in PostgreSQL/SQLite.
    """
    # 1. Seed Allergen
    allergen = Allergen(
        id=uuid.uuid4(),
        allergen_code="lupin",
        allergen_name="Lupin",
        category="Legume",
        severity_default="severe",
    )
    db_session.add(allergen)

    # 2. Seed Ingredient
    ingredient = Ingredient(
        id=uuid.uuid4(),
        standard_name="lupin flour",
        category="Flour",
    )
    db_session.add(ingredient)
    db_session.commit()

    # 3. Seed Mapping
    mapping = IngredientAllergenMap(
        id=uuid.uuid4(),
        ingredient_id=ingredient.id,
        allergen_id=allergen.id,
        cross_reactivity_risk="direct",
        notes="High risk direct derivative of lupin legume",
    )
    db_session.add(mapping)
    db_session.commit()

    # 4. Query through AllergenEngine with active DB session
    matches = allergen_engine.match_allergens_for_ingredients(
        ingredients=["organic lupin flour"],
        db=db_session,
    )

    assert len(matches) > 0
    matched = matches[0]
    assert matched["allergen_code"] == "lupin"
    assert matched["allergen_name"] == "Lupin"
    assert matched["severity_default"] == "severe"


def test_database_backed_additive_lookup(db_session: Session):
    """
    Validates DB lookup for custom or extended E-number additives.
    """
    custom_additive = Additive(
        id=uuid.uuid4(),
        e_number="E999",
        standard_name="Quillaia Extract",
        category="Emulsifier",
        risk_level="caution",
        explanation="Foaming agent used in beverages; monitored for stomach sensitivity.",
    )
    db_session.add(custom_additive)
    db_session.commit()

    results = allergen_engine.match_additives(["E999"], db=db_session)

    assert len(results) == 1
    add = results[0]
    assert add["e_number"] == "E999"
    assert add["name"] == "Quillaia Extract"
    assert add["category"] == "Emulsifier"
    assert add["risk_level"] == "caution"

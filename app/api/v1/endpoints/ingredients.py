from typing import Any, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.knowledge_base.allergen_engine import CORE_ALLERGEN_TAXONOMY, KNOWN_ADDITIVES

router = APIRouter()


@router.get(
    "/allergens",
    status_code=status.HTTP_200_OK,
    summary="Get standard taxonomy list of supported food allergens",
)
def get_supported_allergens():
    results = []
    for code, data in CORE_ALLERGEN_TAXONOMY.items():
        results.append({
            "allergen_code": code,
            "allergen_name": data["name"],
            "default_severity": data["default_severity"],
            "synonyms": data["synonyms"],
        })
    return results


@router.get(
    "/additives",
    status_code=status.HTTP_200_OK,
    summary="Get database list of tracked food additives and E-numbers",
)
def get_tracked_additives():
    results = []
    for code, data in KNOWN_ADDITIVES.items():
        results.append({
            "e_number": code,
            "name": data["name"],
            "category": data["category"],
            "risk_level": data["risk"],
            "explanation": data["explanation"],
        })
    return results

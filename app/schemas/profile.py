import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AllergenItem(BaseModel):
    allergen_id: str = Field(..., description="Unique allergen code (e.g. peanut, milk, gluten)")
    name: str = Field(..., description="Display name of the allergen")
    severity: str = Field("severe", description="Severity constraint: severe, moderate, mild")
    notes: Optional[str] = Field(None, description="Clinical or personal notes")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        norm = v.lower().strip()
        if norm not in ("severe", "moderate", "mild"):
            raise ValueError("Severity must be one of: severe, moderate, mild")
        return norm


class ProfileCreate(BaseModel):
    profile_name: str = Field(..., min_length=1, max_length=100, description="Name of profile (e.g. Dilshan, Child)")
    is_primary: bool = Field(False, description="Set as the default scanning profile")
    active_allergens: List[AllergenItem] = Field(default_factory=list, description="List of monitored allergen constraints")
    notes: Optional[str] = Field(None, description="General dietary notes or medical advice")


class ProfileUpdate(BaseModel):
    profile_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_primary: Optional[bool] = None
    active_allergens: Optional[List[AllergenItem]] = None
    notes: Optional[str] = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    profile_name: str
    is_primary: bool
    active_allergens: List[AllergenItem]
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

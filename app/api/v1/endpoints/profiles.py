import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileOut
from app.services.profile_service import profile_service
from app.api.v1.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.get(
    "",
    response_model=List[ProfileOut],
    status_code=status.HTTP_200_OK,
    summary="List all dietary profiles for current user",
)
def list_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profiles = profile_service.get_profiles_by_user(db, current_user.id)
    return [ProfileOut.model_validate(p) for p in profiles]


@router.post(
    "",
    response_model=ProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new family or dietary profile (max 5 per account)",
)
def create_profile(
    profile_in: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = profile_service.create_profile(db, current_user.id, profile_in)
    return ProfileOut.model_validate(profile)


@router.get(
    "/{profile_id}",
    response_model=ProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific dietary profile",
)
def get_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = profile_service.get_profile_by_id(db, profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dietary profile not found or access denied.",
        )
    return ProfileOut.model_validate(profile)


@router.put(
    "/{profile_id}",
    response_model=ProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Update allergen constraints or metadata for a dietary profile",
)
def update_profile(
    profile_id: uuid.UUID,
    profile_in: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = profile_service.update_profile(db, profile_id, current_user.id, profile_in)
    return ProfileOut.model_validate(updated)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dietary profile",
)
def delete_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile_service.delete_profile(db, profile_id, current_user.id)
    return None

import uuid
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.profile import Profile
from app.schemas.profile import ProfileCreate, ProfileUpdate

MAX_PROFILES_PER_USER = 5


class ProfileService:
    @staticmethod
    def get_profiles_by_user(db: Session, user_id: uuid.UUID) -> List[Profile]:
        return db.query(Profile).filter(Profile.user_id == user_id).order_by(Profile.is_primary.desc(), Profile.created_at.asc()).all()

    @staticmethod
    def get_profile_by_id(db: Session, profile_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Profile]:
        return db.query(Profile).filter(Profile.id == profile_id, Profile.user_id == user_id).first()

    @staticmethod
    def create_profile(db: Session, user_id: uuid.UUID, profile_in: ProfileCreate) -> Profile:
        existing_count = db.query(Profile).filter(Profile.user_id == user_id).count()
        if existing_count >= MAX_PROFILES_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum limit of {MAX_PROFILES_PER_USER} profiles reached for this account.",
            )

        # If this profile is marked primary or it's the very first profile, unset any existing primary profile
        if profile_in.is_primary or existing_count == 0:
            db.query(Profile).filter(Profile.user_id == user_id).update({"is_primary": False})

        new_profile = Profile(
            id=uuid.uuid4(),
            user_id=user_id,
            profile_name=profile_in.profile_name,
            is_primary=profile_in.is_primary or (existing_count == 0),
            active_allergens=[item.model_dump() for item in profile_in.active_allergens],
            notes=profile_in.notes,
        )
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)
        return new_profile

    @staticmethod
    def update_profile(
        db: Session,
        profile_id: uuid.UUID,
        user_id: uuid.UUID,
        profile_in: ProfileUpdate,
    ) -> Profile:
        profile = ProfileService.get_profile_by_id(db, profile_id, user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dietary profile not found or access denied.",
            )

        if profile_in.profile_name is not None:
            profile.profile_name = profile_in.profile_name

        if profile_in.notes is not None:
            profile.notes = profile_in.notes

        if profile_in.active_allergens is not None:
            profile.active_allergens = [item.model_dump() for item in profile_in.active_allergens]

        if profile_in.is_primary is True:
            # Unset all other primary profiles for this user
            db.query(Profile).filter(Profile.user_id == user_id).update({"is_primary": False})
            profile.is_primary = True
        elif profile_in.is_primary is False:
            profile.is_primary = False

        db.commit()
        db.refresh(profile)
        return profile

    @staticmethod
    def delete_profile(db: Session, profile_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        profile = ProfileService.get_profile_by_id(db, profile_id, user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dietary profile not found or access denied.",
            )

        db.delete(profile)
        db.commit()
        return True


profile_service = ProfileService()

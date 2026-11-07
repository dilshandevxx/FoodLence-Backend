import uuid
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.profile import Profile
from app.schemas.auth import UserRegister
from app.core.security import get_password_hash, verify_password


class UserService:
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email.lower().strip()).first()

    @staticmethod
    def get_by_id(db: Session, user_id: uuid.UUID) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create(db: Session, user_in: UserRegister) -> User:
        user = User(
            id=uuid.uuid4(),
            email=user_in.email.lower().strip(),
            password_hash=get_password_hash(user_in.password),
            full_name=user_in.full_name,
            is_active=True,
        )
        db.add(user)
        db.flush()

        # Create an initial primary profile automatically
        default_profile_name = user_in.full_name or "Primary Profile"
        primary_profile = Profile(
            id=uuid.uuid4(),
            user_id=user.id,
            profile_name=default_profile_name,
            is_primary=True,
            active_allergens=[],
            notes="Default profile created upon registration.",
        )
        db.add(primary_profile)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> Optional[User]:
        user = UserService.get_by_email(db, email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user


user_service = UserService()

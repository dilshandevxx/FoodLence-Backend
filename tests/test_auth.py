import pytest
from sqlalchemy.orm import Session
from app.schemas.auth import UserRegister, UserLogin, TokenRefreshRequest
from app.api.v1.endpoints.auth import register, login, refresh_token, get_current_user_profile
from app.services.user_service import user_service
from app.models.profile import Profile
from fastapi import HTTPException


def test_register_new_user(db_session: Session):
    user_in = UserRegister(
        email="dilshan_test@foodlence.com",
        password="secretpassword123",
        full_name="Dilshan Test",
    )
    res = register(user_in, db=db_session)
    assert res.access_token is not None
    assert res.refresh_token is not None
    assert res.user.email == "dilshan_test@foodlence.com"
    assert res.user.full_name == "Dilshan Test"

    # Verify primary profile was auto-created upon registration
    profiles = db_session.query(Profile).filter(Profile.user_id == res.user.id).all()
    assert len(profiles) == 1
    assert profiles[0].is_primary is True


def test_register_duplicate_email(db_session: Session):
    user_in = UserRegister(
        email="duplicate@foodlence.com",
        password="password123",
        full_name="Duplicate User",
    )
    register(user_in, db=db_session)

    with pytest.raises(HTTPException) as exc:
        register(user_in, db=db_session)
    assert exc.value.status_code == 400


def test_login_success(db_session: Session):
    user_in = UserRegister(
        email="login_user@foodlence.com",
        password="password123",
        full_name="Login User",
    )
    register(user_in, db=db_session)

    creds = UserLogin(email="login_user@foodlence.com", password="password123")
    res = login(creds, db=db_session)
    assert res.access_token is not None
    assert res.user.email == "login_user@foodlence.com"


def test_login_invalid_password(db_session: Session):
    user_in = UserRegister(
        email="wrong_pass@foodlence.com",
        password="correctpassword",
        full_name="Wrong Pass User",
    )
    register(user_in, db=db_session)

    creds = UserLogin(email="wrong_pass@foodlence.com", password="wrongpassword")
    with pytest.raises(HTTPException) as exc:
        login(creds, db=db_session)
    assert exc.value.status_code == 401


def test_refresh_token(db_session: Session):
    user_in = UserRegister(
        email="refresh_test@foodlence.com",
        password="password123",
        full_name="Refresh User",
    )
    tokens = register(user_in, db=db_session)

    refresh_req = TokenRefreshRequest(refresh_token=tokens.refresh_token)
    refreshed = refresh_token(refresh_req, db=db_session)
    assert refreshed.access_token is not None
    assert refreshed.token_type == "bearer"
    assert refreshed.expires_in > 0


def test_get_current_user_profile(db_session: Session):
    user = user_service.create(
        db_session,
        UserRegister(email="me_test@foodlence.com", password="password123", full_name="Me User"),
    )
    me_out = get_current_user_profile(current_user=user)
    assert me_out.id == user.id
    assert me_out.email == "me_test@foodlence.com"

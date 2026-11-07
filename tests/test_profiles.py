import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.schemas.auth import UserRegister
from app.schemas.profile import ProfileCreate, ProfileUpdate, AllergenItem
from app.services.user_service import user_service
from app.api.v1.endpoints.profiles import (
    list_profiles,
    create_profile,
    get_profile,
    update_profile,
    delete_profile,
)


def test_list_and_create_profiles(db_session: Session):
    user = user_service.create(
        db_session,
        UserRegister(email="profile_user@foodlence.com", password="password123", full_name="Family Lead"),
    )

    # Initial profile list has default primary profile
    initial = list_profiles(db=db_session, current_user=user)
    assert len(initial) == 1
    assert initial[0].is_primary is True

    # Create second profile: Child with severe peanut and milk allergies
    child_in = ProfileCreate(
        profile_name="Child Profile",
        is_primary=False,
        active_allergens=[
            AllergenItem(allergen_id="peanut", name="Peanuts", severity="severe"),
            AllergenItem(allergen_id="milk", name="Milk & Dairy", severity="moderate"),
        ],
        notes="Carries EpiPen",
    )
    new_prof = create_profile(child_in, db=db_session, current_user=user)
    assert new_prof.profile_name == "Child Profile"
    assert len(new_prof.active_allergens) == 2
    assert new_prof.active_allergens[0].severity == "severe"

    # Total profiles is now 2
    all_profs = list_profiles(db=db_session, current_user=user)
    assert len(all_profs) == 2


def test_enforce_max_5_profiles_limit(db_session: Session):
    user = user_service.create(
        db_session,
        UserRegister(email="limit_user@foodlence.com", password="password123", full_name="Limit Test"),
    )
    # Already has 1 default profile. Create 4 more to hit limit 5.
    for i in range(1, 5):
        create_profile(ProfileCreate(profile_name=f"Profile {i}"), db=db_session, current_user=user)

    assert len(list_profiles(db=db_session, current_user=user)) == 5

    # 6th profile must raise 400 Bad Request
    with pytest.raises(HTTPException) as exc:
        create_profile(ProfileCreate(profile_name="Profile 6"), db=db_session, current_user=user)
    assert exc.value.status_code == 400
    assert "Maximum limit of 5 profiles" in exc.value.detail


def test_update_profile(db_session: Session):
    user = user_service.create(
        db_session,
        UserRegister(email="update_user@foodlence.com", password="password123", full_name="Update Test"),
    )
    prof = create_profile(ProfileCreate(profile_name="Old Name"), db=db_session, current_user=user)

    update_in = ProfileUpdate(
        profile_name="New Name",
        notes="Updated notes",
        active_allergens=[AllergenItem(allergen_id="egg", name="Eggs", severity="severe")],
    )
    updated = update_profile(prof.id, update_in, db=db_session, current_user=user)
    assert updated.profile_name == "New Name"
    assert len(updated.active_allergens) == 1
    assert updated.active_allergens[0].allergen_id == "egg"


def test_delete_profile(db_session: Session):
    user = user_service.create(
        db_session,
        UserRegister(email="delete_user@foodlence.com", password="password123", full_name="Delete Test"),
    )
    prof = create_profile(ProfileCreate(profile_name="Temporary Profile"), db=db_session, current_user=user)
    assert len(list_profiles(db=db_session, current_user=user)) == 2

    delete_profile(prof.id, db=db_session, current_user=user)
    assert len(list_profiles(db=db_session, current_user=user)) == 1


def test_tenant_isolation_between_users(db_session: Session):
    """
    Validates that User A cannot view, update, or delete User B's profiles.
    """
    user_a = user_service.create(db_session, UserRegister(email="user_a@foodlence.com", password="password123"))
    user_b = user_service.create(db_session, UserRegister(email="user_b@foodlence.com", password="password123"))

    prof_a = create_profile(ProfileCreate(profile_name="User A Secret Profile"), db=db_session, current_user=user_a)

    # User B attempting to view User A's profile raises 404
    with pytest.raises(HTTPException) as exc:
        get_profile(prof_a.id, db=db_session, current_user=user_b)
    assert exc.value.status_code == 404

    # User B attempting to delete User A's profile raises 404
    with pytest.raises(HTTPException) as exc:
        delete_profile(prof_a.id, db=db_session, current_user=user_b)
    assert exc.value.status_code == 404

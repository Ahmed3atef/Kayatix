import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models import User
from app.services.auth_service import (
    authenticate_user,
    bootstrap_default_admin,
    create_access_token,
    create_user,
    decode_access_token,
    delete_user,
    get_all_users,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    update_user_permissions,
    verify_password,
)


def test_password_hashing_and_verification():
    raw_pass = "MySecretPass123!"
    hashed = hash_password(raw_pass)
    assert hashed.startswith("pbkdf2:sha256:")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_creation_and_decoding():
    payload = {"sub": "42", "email": "test@example.com", "role": "recruiter"}
    token = create_access_token(payload)
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "42"
    assert decoded["email"] == "test@example.com"
    assert decoded["role"] == "recruiter"
    assert "exp" in decoded

    # Tampered token test
    tampered = token[:-4] + "abcd"
    assert decode_access_token(tampered) is None


@pytest.mark.asyncio
async def test_user_creation_and_auth_service(db_session):
    user = await create_user(
        db=db_session,
        email="recruiter@kayatix.local",
        password="RecruiterPass123!",
        full_name="Alex Recruiter",
        role="recruiter",
    )
    assert user.id is not None
    assert user.email == "recruiter@kayatix.local"
    assert user.role == "recruiter"
    assert user.is_admin is False
    assert user.is_active is True

    # Authenticate successfully
    auth_user = await authenticate_user(db_session, "recruiter@kayatix.local", "RecruiterPass123!")
    assert auth_user is not None
    assert auth_user.id == user.id

    # Authenticate with wrong password
    failed_auth = await authenticate_user(db_session, "recruiter@kayatix.local", "WrongPass!")
    assert failed_auth is None


@pytest.mark.asyncio
async def test_bootstrap_default_admin(db_session, monkeypatch):
    # Simulate .env administrator configuration
    monkeypatch.setattr("app.core.config.settings.ADMIN_EMAIL", "sysadmin@kayatix.local")
    monkeypatch.setattr("app.core.config.settings.ADMIN_PASSWORD", "SuperSecureAdminPass999!")
    monkeypatch.setattr("app.core.config.settings.ADMIN_FULL_NAME", "Root System Admin")

    admin = await bootstrap_default_admin(db_session)
    assert admin is not None
    assert admin.email == "sysadmin@kayatix.local"
    assert admin.role == "admin"
    assert admin.is_admin is True
    assert admin.permissions.get("can_manage_users") is True

    # Verify idempotency
    admin_second_run = await bootstrap_default_admin(db_session)
    assert admin_second_run.id == admin.id


@pytest.mark.asyncio
async def test_auth_api_signup_and_login_endpoints(db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Signup new user
        signup_payload = {
            "full_name": "New Member",
            "email": "member1@kayatix.local",
            "password": "MemberPass123!",
        }
        res = await ac.post("/api/v1/auth/signup", json=signup_payload)
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["user"]["email"] == "member1@kayatix.local"
        assert data["user"]["role"] == "member"
        assert "kayatix_token" in res.cookies

        # 2. Login with correct credentials
        login_payload = {
            "email": "member1@kayatix.local",
            "password": "MemberPass123!",
        }
        login_res = await ac.post("/api/v1/auth/login", json=login_payload)
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        # 3. Access /api/v1/auth/me using Bearer token
        me_res = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "member1@kayatix.local"

        # 4. Login with invalid password
        bad_login = await ac.post(
            "/api/v1/auth/login",
            json={"email": "member1@kayatix.local", "password": "WrongPassword!"},
        )
        assert bad_login.status_code == 401


@pytest.mark.asyncio
async def test_user_management_permissions_and_deletion(db_session):
    # Create an admin user and a standard member user
    admin_user = await create_user(
        db=db_session,
        email="boss@kayatix.local",
        password="BossPassword123!",
        full_name="Boss Admin",
        role="admin",
    )
    admin_token = create_access_token({"sub": str(admin_user.id), "email": admin_user.email, "role": "admin"})

    member_user = await create_user(
        db=db_session,
        email="junior@kayatix.local",
        password="JuniorPassword123!",
        full_name="Junior Dev",
        role="member",
    )
    member_token = create_access_token({"sub": str(member_user.id), "email": member_user.email, "role": "member"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Non-admin attempting to list users -> 403 Forbidden
        forbidden_res = await ac.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert forbidden_res.status_code == 403

        # Admin listing users -> 200 OK
        list_res = await ac.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_res.status_code == 200
        users_list = list_res.json()
        assert len(users_list) >= 2

        # Admin updating member permissions to recruiter
        update_payload = {
            "role": "recruiter",
            "permissions": {"can_screen": True, "can_source": True},
        }
        update_res = await ac.put(
            f"/api/v1/users/{member_user.id}/permissions",
            json=update_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["role"] == "recruiter"
        assert updated_data["permissions"]["can_source"] is True

        # Admin attempting to delete oneself -> 400 Bad Request
        self_del_res = await ac.delete(
            f"/api/v1/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert self_del_res.status_code == 400

        # Admin deleting member user -> 200 OK
        del_res = await ac.delete(
            f"/api/v1/users/{member_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert del_res.status_code == 200

        # Confirm user is deleted
        get_res = await ac.get(
            f"/api/v1/users/{member_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_res.status_code == 404

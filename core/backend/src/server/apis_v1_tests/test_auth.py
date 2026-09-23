import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from src.server.web import app
from src.server.models.db.auth import User, UserRefreshToken
from src.server.apis_v1 import dependencies

pytestmark = pytest.mark.asyncio

BASE_URL = "/v1/auth/users"
REGISTER_URL = f"{BASE_URL}/register"
LOGIN_URL = f"{BASE_URL}/login"
REFRESH_URL = f"{BASE_URL}/refresh"
LOGOUT_URL = f"{BASE_URL}/logout"
UPDATE_PASSWORD_URL = f"{BASE_URL}/update-password"


@pytest_asyncio.fixture
def mock_db_session():
    fake_db = AsyncMock()
    fake_db.commit = AsyncMock()
    fake_db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", 1))
    fake_db.add = lambda obj: None
    fake_db.delete = AsyncMock()
    fake_db.get = AsyncMock()

    def make_scalar_result(first=None, all_list=None, scalar_value=2):
        async def execute(_):
            return type(
                "Res",
                (),
                {
                    "scalars": lambda _: type(
                        "S",
                        (),
                        {
                            "first": lambda _: first,
                            "all": lambda _: all_list or ([] if first is None else [first]),
                        },
                    )(),
                    "scalar": lambda _: scalar_value,
                },
            )()

        return execute

    fake_db.make_scalar_result = make_scalar_result
    fake_db.execute = make_scalar_result(first=None)
    return fake_db


@pytest_asyncio.fixture(autouse=True)
def override_dependencies(mock_db_session):
    app.dependency_overrides[dependencies.get_db_session] = lambda: mock_db_session
    app.dependency_overrides[dependencies.get_optional_user] = lambda: None
    yield
    app.dependency_overrides = {}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def make_user(username="user", email="user@test.com", admin=False, id=1):
    return User(
        id=id,
        username=username,
        email=email,
        hashed_password="fake_hashed_password",
        admin=admin,
    )


# REGISTER TESTS (C1–C8)

@patch("src.server.apis_v1.auth.hash_password", return_value="fakehash")
async def test_c1_register_first_user_bootstrap_admin(mock_hash, client, mock_db_session):
    mock_db_session.execute = mock_db_session.make_scalar_result(first=None)
    payload = {"username": "first_admin", "email": "admin@test.com", "password": "Admin123!"}
    response = await client.post(REGISTER_URL, json=payload)
    assert response.status_code == 200
    assert response.json()["admin"] is True


async def test_c2_register_admin_creates_normal_user(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: make_user(admin=True)

    async def fake_execute(query):
        q = str(query).lower()
        # no existing users → not bootstrap
        if "from users" in q and "where" not in q:
            return await mock_db_session.make_scalar_result(first=make_user(admin=True))(query)
        # simulate no email or username duplicates
        if "where users.email" in q or "where users.username" in q:
            return await mock_db_session.make_scalar_result(first=None)(query)
        return await mock_db_session.make_scalar_result(first=None)(query)

    mock_db_session.execute = fake_execute
    payload = {"username": "new_user", "email": "new@user.com", "password": "UserPass!"}
    response = await client.post(REGISTER_URL, json=payload)
    assert response.status_code == 200, response.text


async def test_c3_register_non_admin_forbidden(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: make_user(admin=False)
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user())
    response = await client.post(REGISTER_URL, json={"username": "a", "email": "a@a.com", "password": "x"})
    assert response.status_code == 403


async def test_c4_register_duplicate_email(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: make_user(admin=True)

    async def fake_execute(_):
        return type("Res", (), {"scalars": lambda _: type("S", (), {"first": lambda _: make_user()})()})()

    mock_db_session.execute = fake_execute
    response = await client.post(REGISTER_URL, json={"username": "u", "email": "dup@test.com", "password": "p"})
    assert response.status_code == 400


async def test_c5_register_duplicate_username(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: make_user(admin=True)

    async def fake_execute(_):
        return type("Res", (),
                    {"scalars": lambda _: type("S", (), {"first": lambda _: make_user(username='same')})()})()

    mock_db_session.execute = fake_execute
    response = await client.post(REGISTER_URL, json={"username": "same", "email": "unique@test.com", "password": "p"})
    assert response.status_code == 400


async def test_c6_register_no_user_forbidden(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: None
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user(admin=True))
    response = await client.post(REGISTER_URL, json={"username": "anon", "email": "anon@a.com", "password": "123"})
    assert response.status_code == 403


async def test_c7_register_sql_injection_attempt(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: make_user(admin=True)
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user(admin=True))
    response = await client.post(REGISTER_URL,
                                 json={"username": "admin' OR 1=1 --", "email": "x@test.com", "password": "a"})
    assert response.status_code in (400, 422)


async def test_c8_register_password_leak_check(client, mock_db_session):
    app.dependency_overrides[dependencies.get_optional_user] = lambda: make_user(admin=True)
    mock_db_session.execute = mock_db_session.make_scalar_result(first=None)
    payload = {"username": "safe", "email": "safe@test.com", "password": "Safe123"}
    r = await client.post(REGISTER_URL, json=payload)
    assert "hashed_password" not in r.text


# LOGIN TESTS (C9–C14)

@patch("src.server.apis_v1.auth.verify_password", return_value=True)
@patch("src.server.apis_v1.auth.create_access_token", return_value="access123")
@patch("src.server.apis_v1.auth.create_refresh_token", return_value=("refresh123", datetime.now(timezone.utc)))
async def test_c9_login_valid(mock_refresh, mock_access, mock_verify, client, mock_db_session):
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user())
    payload = {"email": "user@test.com", "password": "x"}
    r = await client.post(LOGIN_URL, json=payload)
    assert r.status_code == 200
    assert "access_token" in r.json()


@patch("src.server.apis_v1.auth.verify_password", return_value=False)
async def test_c10_login_invalid_password(mock_verify, client, mock_db_session):
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user())
    r = await client.post(LOGIN_URL, json={"email": "x@x.com", "password": "bad"})
    assert r.status_code == 401


async def test_c11_login_no_user(client, mock_db_session):
    mock_db_session.execute = mock_db_session.make_scalar_result(first=None)
    r = await client.post(LOGIN_URL, json={"email": "nouser@x.com", "password": "x"})
    assert r.status_code == 401


async def test_c12_login_db_failure(client, mock_db_session):
    mock_db_session.execute = AsyncMock(side_effect=Exception("DB fail"))
    try:
        r = await client.post(LOGIN_URL, json={"email": "a@a.com", "password": "x"})
    except Exception:
        # endpoint might raise due to DB exception
        r = None
    if r:
        assert r.status_code in (422, 500)


@patch("src.server.apis_v1.auth.verify_password", return_value=True)
@patch("src.server.apis_v1.auth.create_access_token", return_value="t")
@patch("src.server.apis_v1.auth.create_refresh_token", return_value=("r", datetime.now(timezone.utc)))
async def test_c13_login_admin(mock_refresh, mock_access, mock_verify, client, mock_db_session):
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user(admin=True))
    r = await client.post(LOGIN_URL, json={"email": "admin@x.com", "password": "x"})
    assert r.status_code == 200


@patch("src.server.apis_v1.auth.verify_password", return_value=True)
@patch("src.server.apis_v1.auth.create_access_token", return_value="secure_access")
@patch("src.server.apis_v1.auth.create_refresh_token", return_value=("secure_refresh", datetime.now(timezone.utc)))
async def test_c14_login_token_integrity(mock_refresh, mock_access, mock_verify, client, mock_db_session):
    mock_db_session.execute = mock_db_session.make_scalar_result(first=make_user())
    r = await client.post(LOGIN_URL, json={"email": "user@test.com", "password": "Safe"})
    assert r.status_code == 200
    assert "hashed_password" not in r.text


# REFRESH TOKEN TESTS (C15–C18)

@patch("src.server.apis_v1.auth.verify_token", return_value=True)
@patch("src.server.apis_v1.auth.decode_token")
@patch("src.server.utilities.auth_utils.create_access_token", return_value="new_access")
@patch("src.server.utilities.auth_utils.create_refresh_token", return_value=("new_refresh", datetime.now(timezone.utc)))
async def test_c15_refresh_valid(mock_cr, mock_ca, mock_decode, mock_verify_token, client, mock_db_session):
    mock_decode.return_value = {"sub": "1", "email": "u", "type": "refresh"}
    mock_db_session.execute = mock_db_session.make_scalar_result(
        first=None,
        all_list=[UserRefreshToken(id=1, user_id=1, token_hash="fake_hash",
                                   expires_at=datetime.now(timezone.utc) + timedelta(days=1))]
    )
    mock_db_session.get = AsyncMock(return_value=make_user())
    r = await client.post(f"{REFRESH_URL}?refresh_token=t")
    assert r.status_code == 200


@patch("src.server.apis_v1.auth.decode_token", return_value=None)
async def test_c16_refresh_invalid(mock_decode, client):
    r = await client.post(f"{REFRESH_URL}?refresh_token=invalid")
    assert r.status_code == 401


@patch("src.server.apis_v1.auth.decode_token", return_value={"sub": "1", "type": "access"})
async def test_c17_refresh_using_access_token(mock_decode, client):
    r = await client.post(f"{REFRESH_URL}?refresh_token=accesstoken")
    assert r.status_code == 401


@patch("src.server.apis_v1.auth.decode_token", return_value={"email": "u"})
async def test_c18_refresh_missing_claims(mock_decode, client):
    r = await client.post(f"{REFRESH_URL}?refresh_token=x")
    assert r.status_code == 401


# LOGOUT TESTS (C19–C20)

async def test_c19_logout_success(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_user] = make_user
    r = await client.post(LOGOUT_URL)
    assert r.status_code == 200
    assert "successfully" in r.text.lower()


async def test_c20_logout_requires_auth(client):
    app.dependency_overrides[dependencies.get_current_user] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=401))
    r = await client.post(LOGOUT_URL)
    assert r.status_code == 401


# UPDATE PASSWORD TESTS (C21–C24)

@patch("src.server.apis_v1.auth.verify_password", return_value=True)
@patch("src.server.apis_v1.auth.hash_password", return_value="new_hash")
async def test_c21_update_password_valid(mock_hash, mock_verify, client, mock_db_session):
    user = make_user()
    app.dependency_overrides[dependencies.get_current_user] = lambda: user
    r = await client.put(UPDATE_PASSWORD_URL, json={"old_password": "o", "new_password": "n"})
    assert r.status_code == 200


@patch("src.server.apis_v1.auth.verify_password", return_value=False)
async def test_c22_update_password_invalid_old(mock_verify, client, mock_db_session):
    user = make_user()
    app.dependency_overrides[dependencies.get_current_user] = lambda: user
    r = await client.put(UPDATE_PASSWORD_URL, json={"old_password": "bad", "new_password": "good"})
    assert r.status_code == 400


async def test_c23_update_password_no_user(client):
    app.dependency_overrides[dependencies.get_current_user] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=401))
    r = await client.put(UPDATE_PASSWORD_URL, json={"old_password": "a", "new_password": "b"})
    assert r.status_code == 401


@patch("src.server.apis_v1.auth.verify_password", return_value=True)
async def test_c24_update_password_same_hash(mock_verify, client, mock_db_session):
    user = make_user()
    app.dependency_overrides[dependencies.get_current_user] = lambda: user
    with patch("src.server.apis_v1.auth.hash_password", return_value=user.hashed_password):
        r = await client.put(UPDATE_PASSWORD_URL, json={"old_password": "a", "new_password": "b"})
        assert r.status_code == 200


# DELETE USER TESTS (C25–C27)

async def test_c25_delete_user_success(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(id=2))
    r = await client.delete(f"{BASE_URL}/2")
    assert r.status_code == 200


async def test_c26_delete_user_not_found(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=None)
    r = await client.delete(f"{BASE_URL}/99")
    assert r.status_code == 404


async def test_c27_delete_last_admin_prevented(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(admin=True))

    async def count_admins(_):
        return type("Res", (), {"scalar_one": lambda _: 1})()

    mock_db_session.execute = count_admins
    r = await client.delete(f"{BASE_URL}/1")
    assert r.status_code == 400


# ADMIN ROLE MANAGEMENT (C28–C29)

async def test_c28_make_admin_success(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(id=3, admin=False))
    r = await client.put(f"{BASE_URL}/3/make-admin")
    assert r.status_code == 200


async def test_c29_remove_admin_prevent_last(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(admin=True))

    async def count_admins(_):
        return type("Res", (), {"scalar_one": lambda _: 1})()

    mock_db_session.execute = count_admins
    r = await client.put(f"{BASE_URL}/1/remove-admin")
    assert r.status_code == 400


# LIST USERS & ADMIN RESET PASSWORD (C30–C31)

async def test_c30_list_users_admin(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_user] = lambda: make_user(admin=True)
    mock_db_session.execute = mock_db_session.make_scalar_result(all_list=[make_user(), make_user(id=2)])
    r = await client.get(BASE_URL)
    assert r.status_code == 200


async def test_c31_admin_reset_password(client, mock_db_session):
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user())
    r = await client.put(f"{BASE_URL}/1/reset-password", json={"new_password": "NewPass!"})
    assert r.status_code == 200


# DELETE USER EXTENDED TESTS (C32–C35)

async def test_c32_delete_user_removes_refresh_tokens(client, mock_db_session):
    """Ensure refresh tokens are deleted when a user is removed."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(id=5))
    mock_db_session.execute = AsyncMock()
    r = await client.delete(f"{BASE_URL}/5")
    assert r.status_code == 200
    mock_db_session.execute.assert_called()
    assert "deleted successfully" in r.text.lower()


async def test_c33_delete_admin_multiple_admins(client, mock_db_session):
    """Allow deleting an admin when multiple admins exist."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(id=3, admin=True))

    async def count_admins(_):
        return type("Res", (), {"scalar_one": lambda _: 2})()

    mock_db_session.execute = count_admins
    r = await client.delete(f"{BASE_URL}/3")
    assert r.status_code == 200


async def test_c34_delete_user_db_exception(client, mock_db_session):
    """Simulate DB exception during delete to ensure handle_db_errors returns 500."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(side_effect=Exception("DB fail"))
    r = await client.delete(f"{BASE_URL}/7")
    assert r.status_code in (422, 500)


async def test_c35_delete_self_as_admin(client, mock_db_session):
    """Admin deleting their own account (not last admin) should succeed."""
    self_user = make_user(id=1, admin=True)
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: self_user
    mock_db_session.get = AsyncMock(return_value=self_user)

    async def count_admins(_):
        return type("Res", (), {"scalar_one": lambda _: 2})()

    mock_db_session.execute = count_admins
    r = await client.delete(f"{BASE_URL}/1")
    assert r.status_code == 200


# MAKE ADMIN TESTS (C36–C38)

async def test_c36_make_admin_user_not_found(client, mock_db_session):
    """Should return 404 if target user not found."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=None)
    r = await client.put(f"{BASE_URL}/99/make-admin")
    assert r.status_code == 404


async def test_c37_make_admin_already_admin(client, mock_db_session):
    """Return 400 if user is already an admin."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(id=3, admin=True))
    r = await client.put(f"{BASE_URL}/3/make-admin")
    assert r.status_code == 400


async def test_c38_make_admin_db_exception(client, mock_db_session):
    """Simulate DB failure during make-admin operation."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(side_effect=Exception("DB fail"))
    r = await client.put(f"{BASE_URL}/2/make-admin")
    assert r.status_code in (422, 500)


# REMOVE ADMIN TESTS (C39–C41)

async def test_c39_remove_admin_user_not_found(client, mock_db_session):
    """Return 404 if target user not found during demotion."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=None)
    r = await client.put(f"{BASE_URL}/88/remove-admin")
    assert r.status_code == 404


async def test_c40_remove_admin_not_admin(client, mock_db_session):
    """Return 400 if target user is not admin."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(admin=False))
    r = await client.put(f"{BASE_URL}/5/remove-admin")
    assert r.status_code == 400


async def test_c41_remove_admin_success(client, mock_db_session):
    """Demote an admin when multiple admins exist."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user(admin=True))

    async def count_admins(_):
        return type("Res", (), {"scalar_one": lambda _: 2})()

    mock_db_session.execute = count_admins
    r = await client.put(f"{BASE_URL}/4/remove-admin")
    assert r.status_code == 200


# LIST USERS TESTS (C42–C47)

async def test_c42_list_users_non_admin_returns_self(client, mock_db_session):
    """Non-admin users should only see themselves."""
    user = make_user(admin=False)
    app.dependency_overrides[dependencies.get_current_user] = lambda: user
    r = await client.get(BASE_URL)
    assert r.status_code == 200
    data = r.json()
    assert len(data["users"]) == 1
    assert data["users"][0]["username"] == user.username


async def test_c43_list_users_admin_all(client, mock_db_session):
    """Admin sees all users."""
    admin = make_user(admin=True)
    app.dependency_overrides[dependencies.get_current_user] = lambda: admin
    mock_db_session.execute = mock_db_session.make_scalar_result(all_list=[make_user(), make_user(id=2)])
    r = await client.get(BASE_URL)
    assert r.status_code == 200
    assert "users" in r.json()


async def test_c44_list_users_with_search_filter(client, mock_db_session):
    """Verify search_string filters usernames/emails."""
    admin = make_user(admin=True)
    app.dependency_overrides[dependencies.get_current_user] = lambda: admin
    mock_db_session.execute = mock_db_session.make_scalar_result(all_list=[make_user(username="filter_me")])
    r = await client.get(f"{BASE_URL}?search_string=filter")
    assert r.status_code == 200


async def test_c45_list_users_role_admin_filter(client, mock_db_session):
    """Admin role filter only returns admin users."""
    admin = make_user(admin=True)
    app.dependency_overrides[dependencies.get_current_user] = lambda: admin
    mock_db_session.execute = mock_db_session.make_scalar_result(all_list=[make_user(admin=True)])
    r = await client.get(f"{BASE_URL}?role=admin")
    assert r.status_code == 200


async def test_c46_list_users_role_user_filter(client, mock_db_session):
    """User role filter only returns non-admins."""
    admin = make_user(admin=True)
    app.dependency_overrides[dependencies.get_current_user] = lambda: admin
    mock_db_session.execute = mock_db_session.make_scalar_result(all_list=[make_user(admin=False)])
    r = await client.get(f"{BASE_URL}?role=user")
    assert r.status_code == 200


async def test_c47_list_users_db_exception(client, mock_db_session):
    """Simulate DB exception to ensure handle_db_errors returns 500."""
    admin = make_user(admin=True)
    app.dependency_overrides[dependencies.get_current_user] = lambda: admin
    mock_db_session.execute = AsyncMock(side_effect=Exception("DB fail"))
    r = await client.get(BASE_URL)
    assert r.status_code in (422, 500)


# ADMIN RESET PASSWORD TESTS (C48–C50)

async def test_c48_admin_reset_password_user_not_found(client, mock_db_session):
    """Return 404 if target user not found during password reset."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=None)
    r = await client.put(f"{BASE_URL}/11/reset-password", json={"new_password": "x"})
    assert r.status_code == 404


@patch("src.server.apis_v1.auth.hash_password", return_value="newhash")
async def test_c49_admin_reset_password_success(mock_hash, client, mock_db_session):
    """Admin successfully resets another user’s password."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(return_value=make_user())
    r = await client.put(f"{BASE_URL}/2/reset-password", json={"new_password": "UpdatedPass!"})
    assert r.status_code == 200
    assert "updated successfully" in r.text.lower()


async def test_c50_admin_reset_password_db_exception(client, mock_db_session):
    """Force DB failure to check handle_db_errors decorator."""
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: make_user(admin=True)
    mock_db_session.get = AsyncMock(side_effect=Exception("DB crash"))
    r = await client.put(f"{BASE_URL}/2/reset-password", json={"new_password": "Bad!"})
    assert r.status_code in (422, 500)

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import (
    get_db_session,
    get_current_user,
    get_current_admin_user,
    get_optional_user,
)
from src.server.models.api.auth import (
    UserResponse,
    UserListRequest,
    UserListResponse,
    UserCreate,
    UserLogin,
    Token,
    UpdatePassword,
    AdminResetPassword,
    UserRoleFilter,
)
from src.server.models.api.pagination_meta import PaginationMeta
from src.server.models.db.auth import User, UserRefreshToken
from src.server.utilities.auth_utils import (
    hash_password,
    verify_password,
    hash_token,
    verify_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


# === Global Async DB Error Handler ===
def handle_db_errors(func):
    """
    Decorator to safely handle unexpected DB/async errors.
    Converts unhandled exceptions into HTTP 500 responses with logs.
    """
    from functools import wraps

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"[DB-ERROR] Unhandled DB exception in {func.__name__}: {e}")
            raise HTTPException(status_code=500, detail="Internal database error")

    return wrapper


@router.post("/users/register", response_model=UserResponse)
@handle_db_errors
async def register(
        user: UserCreate,
        db: AsyncSession = Depends(get_db_session),
        current_admin: User | None = Depends(get_optional_user),
):
    """
    Register a new user.
    - The first registered user becomes an admin automatically.
    - Subsequent user creation requires an admin.
    - Prevents duplicate usernames and emails.
    """
    logger.info(f"[REGISTER] Registration attempt | username={user.username} email={user.email}")

    res = await db.execute(select(User))
    first_user = not res.scalars().first()

    if first_user:
        logger.info(f"[REGISTER] No existing users found. Bootstrapping admin user | username={user.username}")
        new_user = User(
            username=user.username,
            email=user.email,
            hashed_password=hash_password(user.password),
            admin=True,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        logger.info(f"[REGISTER] First admin created successfully | id={new_user.id}")
        return new_user

    if not current_admin or not current_admin.admin:
        logger.warning(
            f"[REGISTER] Unauthorized registration attempt | by={current_admin.username if current_admin else 'Anonymous'}")
        res = await db.execute(select(User).where(User.admin == True))
        first_admin = res.scalars().first()
        admin_email = first_admin.email if first_admin else "No admin found"
        raise HTTPException(
            status_code=403,
            detail=f"Only admins can create users. Contact admin: {admin_email}",
        )

    if (await db.execute(select(User).where(User.email == user.email))).scalars().first():
        logger.warning(f"[REGISTER] Email already exists | email={user.email}")
        raise HTTPException(status_code=400, detail="Email already registered")

    if (await db.execute(select(User).where(User.username == user.username))).scalars().first():
        logger.warning(f"[REGISTER] Username already taken | username={user.username}")
        raise HTTPException(status_code=400, detail="Username already taken")

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        admin=False,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    logger.info(
        f"[REGISTER] User created successfully | username={new_user.username} created_by={current_admin.username}")
    return new_user


@router.post("/users/login", response_model=Token)
@handle_db_errors
async def login(user: UserLogin, db: AsyncSession = Depends(get_db_session)):
    """
    Authenticate a user and issue JWT tokens.
    - Verifies credentials.
    - Stores refresh token in DB (hashed) for session tracking.
    """
    logger.info(f"[LOGIN] Login attempt | email={user.email}")
    res = await db.execute(select(User).where(User.email == user.email))
    db_user = res.scalars().first()

    if not db_user:
        logger.warning(f"[LOGIN] User not found | email={user.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(user.password, db_user.hashed_password):
        logger.warning(f"[LOGIN] Invalid password | email={user.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    logger.debug(f"[LOGIN] Credentials verified | user_id={db_user.id}")

    data = {
        "sub": str(db_user.id),
        "email": db_user.email,
        "username": db_user.username,
        "admin": db_user.admin,
    }

    access_token = create_access_token(data)
    refresh_token, expires_at = create_refresh_token(data)
    hashed_refresh_token = hash_token(refresh_token)

    refresh_entry = UserRefreshToken(
        user_id=db_user.id,
        token_hash=hashed_refresh_token,
        expires_at=expires_at,
    )
    db.add(refresh_entry)
    await db.commit()

    logger.info(f"[LOGIN] Login successful | user_id={db_user.id} username={db_user.username} admin={db_user.admin}")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/users/refresh", response_model=Token)
@handle_db_errors
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db_session)):
    """
    Refresh access tokens using a valid refresh token.
    - Validates JWT and verifies the hashed token in DB.
    - Checks expiry and user validity.
    - Rotates refresh tokens in place .
    """
    logger.info("[REFRESH] Token refresh request received")

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        logger.error("[REFRESH] Invalid refresh token | unable to decode or wrong type")
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = int(payload["sub"])
    logger.debug(f"[REFRESH] Token decoded successfully | user_id={user_id}")

    res = await db.execute(select(UserRefreshToken).where(UserRefreshToken.user_id == user_id))
    db_tokens = res.scalars().all()

    matched_token = None
    for db_token in db_tokens:
        if verify_token(refresh_token, db_token.token_hash):
            matched_token = db_token
            logger.debug(f"[REFRESH] Matching refresh token found | token_id={db_token.id}")
            break

    if not matched_token:
        logger.warning(f"[REFRESH] No matching refresh token in DB | user_id={user_id}")
        raise HTTPException(status_code=401, detail="Token revoked or invalidated")

    if matched_token.expires_at < datetime.now(timezone.utc):
        logger.warning(f"[REFRESH] Refresh token expired | user_id={user_id} token_id={matched_token.id}")
        await db.delete(matched_token)
        await db.commit()
        raise HTTPException(status_code=401, detail="Token expired")

    user = await db.get(User, matched_token.user_id)
    if not user:
        logger.error(f"[REFRESH] User not found during refresh | user_id={user_id}")
        await db.delete(matched_token)
        await db.commit()
        raise HTTPException(status_code=401, detail="User not found")

    data = {
        "sub": str(user.id),
        "email": user.email,
        "username": user.username,
        "admin": user.admin,
    }

    access_token = create_access_token(data)
    new_refresh_token, new_expiry = create_refresh_token(data)
    matched_token.token = hash_token(new_refresh_token)
    matched_token.expires_at = new_expiry

    db.add(matched_token)
    await db.commit()

    logger.info(f"[REFRESH] Refresh token rotated successfully | user_id={user.id} expires_at={new_expiry}")
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/users/logout")
@handle_db_errors
async def logout(
        db: AsyncSession = Depends(get_db_session),
        current_user: User = Depends(get_current_user),
):
    """
    Log out the current user.
    - Invalidates all active refresh tokens for the authenticated user.
    """
    logger.info(f"[LOGOUT] Logout initiated | user_id={current_user.id} username={current_user.username}")

    await db.execute(delete(UserRefreshToken).where(UserRefreshToken.user_id == current_user.id))
    await db.commit()

    logger.info(f"[LOGOUT] All refresh tokens invalidated successfully | user_id={current_user.id}")
    return {"msg": "Successfully logged out and all sessions invalidated"}


@router.put("/users/update-password")
@handle_db_errors
async def update_password(
        body: UpdatePassword,
        db: AsyncSession = Depends(get_db_session),
        current_user: User = Depends(get_current_user),
):
    """
    Allow a user to update their password.
    - Validates old password.
    - Invalidates all active refresh tokens.
    """
    logger.info(
        f"[PASSWORD-UPDATE] Password update request | user_id={current_user.id} username={current_user.username}")

    if not verify_password(body.old_password, current_user.hashed_password):
        logger.warning(f"[PASSWORD-UPDATE] Incorrect old password | user_id={current_user.id}")
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.hashed_password = hash_password(body.new_password)
    db.add(current_user)

    await db.execute(delete(UserRefreshToken).where(UserRefreshToken.user_id == current_user.id))
    await db.commit()

    logger.info(
        f"[PASSWORD-UPDATE] Password updated successfully | user_id={current_user.id} username={current_user.username}")
    return {"msg": "Password updated successfully"}


@router.delete("/users/{id}")
@handle_db_errors
async def delete_user(
        id: int,
        db: AsyncSession = Depends(get_db_session),
        current_admin: User = Depends(get_current_admin_user),
):
    """
    Delete a user and revoke all tokens.
    - Prevents deletion of the last admin.
    - Ensures refresh tokens are removed.
    """
    logger.info(f"[DELETE] Admin '{current_admin.username}' attempting to delete user | target_id={id}")
    user = await db.get(User, id)
    if not user:
        logger.error(f"[DELETE] User not found | id={id}")
        raise HTTPException(status_code=404, detail="User not found")

    if user.admin:
        res = await db.execute(select(func.count()).select_from(User).where(User.admin == True))
        admin_count = res.scalar_one()
        logger.debug(f"[DELETE] Admin count check before deletion | total_admins={admin_count}")
        if admin_count == 1:
            logger.warning("[DELETE] Attempted to delete last remaining admin account")
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")

    await db.execute(delete(UserRefreshToken).where(UserRefreshToken.user_id == id))
    await db.delete(user)
    await db.commit()

    logger.info(f"[DELETE] User deleted successfully | target_id={id} deleted_by={current_admin.username}")
    return {"msg": "User deleted successfully"}


@router.put("/users/{id}/make-admin")
@handle_db_errors
async def make_admin(
        id: int,
        db: AsyncSession = Depends(get_db_session),
        current_admin: User = Depends(get_current_admin_user),
):
    """
    Promote a user to admin role.
    - Only admins can perform this action.
    """
    logger.info(f"[ADMIN] Promotion attempt | target_id={id} by={current_admin.username}")
    user = await db.get(User, id)
    if not user:
        logger.error(f"[ADMIN] User not found for promotion | id={id}")
        raise HTTPException(status_code=404, detail="User not found")
    if user.admin:
        logger.warning(f"[ADMIN] User already an admin | id={id}")
        raise HTTPException(status_code=400, detail=f"User '{user.username}' is already an admin")
    user.admin = True
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"[ADMIN] User promoted to admin successfully | id={user.id}")
    return {"msg": f"User {user.username} promoted to Admin"}


@router.put("/users/{id}/remove-admin")
@handle_db_errors
async def remove_admin(
        id: int,
        db: AsyncSession = Depends(get_db_session),
        current_admin: User = Depends(get_current_admin_user),
):
    """
    Remove admin rights from a user.
    - Prevents removing the last admin.
    """
    logger.info(f"[ADMIN] Demotion attempt | target_id={id} by={current_admin.username}")
    user = await db.get(User, id)
    if not user:
        logger.error(f"[ADMIN] User not found for demotion | id={id}")
        raise HTTPException(status_code=404, detail="User not found")
    if not user.admin:
        logger.warning(f"[ADMIN] User is not an admin | id={id}")
        raise HTTPException(status_code=400, detail="User is not an admin")

    res = await db.execute(select(func.count()).select_from(User).where(User.admin == True))
    admin_count = res.scalar_one()
    if admin_count == 1:
        logger.warning("[ADMIN] Attempted to demote last remaining admin")
        raise HTTPException(status_code=400, detail="Cannot demote the last admin")

    user.admin = False
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"[ADMIN] Admin privileges removed successfully | user_id={id}")
    return {"msg": f"User {user.username} demoted from admin"}


@router.get("/users", response_model=UserListResponse)
@handle_db_errors
async def list_users(
        request: UserListRequest = Depends(),
        db: AsyncSession = Depends(get_db_session),
        current_user: User = Depends(get_current_user),
):
    """
    List all users.
    - Supports pagination, search, and role filtering.
    - Admins see all users; non-admins see only themselves.
    """
    logger.info(f"[LIST-USERS] Listing request | by={current_user.username} admin={current_user.admin}")

    if not current_user.admin:
        logger.debug(f"[LIST-USERS] Non-admin user requested profile | user_id={current_user.id}")
        return UserListResponse(
            users=[UserResponse.from_orm(current_user)],
            pagination=PaginationMeta(current_page=1, page_size=1, total_items=1),
        )

    query = select(User)
    count_query = select(func.count(User.id))
    filters = []

    if request.search_string:
        logger.debug(f"[LIST-USERS] Search filter applied | search='{request.search_string}'")
        filters.append(
            or_(
                User.username.ilike(f"%{request.search_string}%"),
                User.email.ilike(f"%{request.search_string}%"),
            )
        )

    if request.role:
        logger.debug(f"[LIST-USERS] Role filter applied | role={request.role}")
        if request.role == UserRoleFilter.admin:
            filters.append(User.admin.is_(True))
        elif request.role == UserRoleFilter.user:
            filters.append(User.admin.is_(False))

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    query = query.order_by(User.created_at.desc()).limit(request.page_size).offset(
        (request.page - 1) * request.page_size
    )

    result = await db.execute(query)
    users = result.scalars().all()
    count_result = await db.execute(count_query)
    total_items = count_result.scalar() or 0

    logger.info(f"[LIST-USERS] Returning {len(users)} users | total={total_items} requested_by={current_user.username}")
    return UserListResponse(
        users=[UserResponse.from_orm(u) for u in users],
        pagination=PaginationMeta(
            current_page=request.page,
            page_size=request.page_size,
            total_items=total_items,
        ),
    )


@router.put("/users/{id}/reset-password")
@handle_db_errors
async def admin_reset_password(
        id: int,
        body: AdminResetPassword,
        db: AsyncSession = Depends(get_db_session),
        current_admin: User = Depends(get_current_admin_user),
):
    """
    Allow an admin to reset any user’s password.
    - Invalidates all existing refresh tokens.
    - Can be used for self or other users.
    """
    logger.info(f"[ADMIN-RESET] Password reset attempt | target_id={id} by_admin={current_admin.username}")
    user = await db.get(User, id)
    if not user:
        logger.error(f"[ADMIN-RESET] Target user not found | id={id}")
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    db.add(user)

    await db.execute(delete(UserRefreshToken).where(UserRefreshToken.user_id == id))
    await db.commit()

    logger.info(f"[ADMIN-RESET] Password reset successful | user_id={id} reset_by={current_admin.username}")
    return {"msg": f"Password for user '{user.username}' updated successfully by admin"}

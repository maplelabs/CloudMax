from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_current_user, get_db_session
from src.server.models.api.auth import UserResponse
from src.server.models.db.auth import User

router = APIRouter(tags=["users"])


@router.get("/{id}/profile", response_model=UserResponse)
async def profile(
        id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db_session),
):
    """
    Fetch profile of a user.
    - Admins can fetch any profile
    - Non-admins can only fetch their own profile
    """
    if not current_user.admin and current_user.id != id:
        raise HTTPException(status_code=403, detail="Not authorized to view this profile")

    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

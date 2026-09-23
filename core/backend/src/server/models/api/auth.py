from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, EmailStr, ConfigDict

from src.server.models.api.pagination_meta import PaginationMeta


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    # admin: Optional[bool] = False   # <-- allow client to request admin role


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    admin: bool  # added admin
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UpdatePassword(BaseModel):
    old_password: str
    new_password: str


class UserRoleFilter(str, Enum):
    admin = "admin"
    user = "user"


class UserListRequest(BaseModel):
    page: int = 1
    page_size: int = 10
    search_string: Optional[str] = None
    role: Optional[UserRoleFilter] = None


class UserListResponse(BaseModel):
    users: List[UserResponse]
    pagination: PaginationMeta


class AdminResetPassword(BaseModel):
    new_password: str

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import jwt
from passlib.context import CryptContext

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "changeme")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash plain password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """Hash refresh token before storing in DB."""
    return pwd_context.hash(token)


def verify_token(plain_token: str, hashed_token: str) -> bool:
    """Verify a provided refresh token against its stored hash."""
    return pwd_context.verify(plain_token, hashed_token)


# Token creation
def create_access_token(data: Dict[str, Any]) -> str:
    """
    Create a short-lived JWT access token.
    Expected keys in data: sub (user_id), email, admin
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


import uuid


def create_refresh_token(data: Dict[str, Any]) -> tuple[str, datetime]:
    """
    Create a long-lived JWT refresh token with unique ID and expiry.
    Returns (token, expires_at)
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    })
    token = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, expire


# Token decoding

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode a JWT token and return its payload if valid,
    otherwise return None.
    """
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

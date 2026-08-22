import os
import sys
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, EmailStr, Field
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from dotenv import load_dotenv

# Try importing python-jose or PyJWT
try:
    from jose import JWTError, jwt
except ImportError:
    import jwt
    class JWTError(Exception):
        pass

load_dotenv()

# =====================================================================
# 1. Security Configuration
# =====================================================================

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "finsight-regtech-jwt-secret-2026-super-secure-cryptographic-signing-key"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 Hours default

# Password Hashing Context
security_bearer = HTTPBearer(auto_error=False)


# =====================================================================
# 2. Enums and Pydantic Schemas
# =====================================================================

class UserRole(str, Enum):
    DEVELOPER = "DEVELOPER"
    MANAGER = "MANAGER"
    MASTER_ADMIN = "MASTER_ADMIN"


class CurrentUser(BaseModel):
    id: str = Field(..., description="UUID string of the user")
    org_id: str = Field(..., description="UUID string of the user's organization")
    email: str = Field(..., description="User's unique email address")
    role: UserRole = Field(..., description="Role-Based Access Control tier")
    org_name: Optional[str] = Field(None, description="Human-readable organization name")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]
    organization: Optional[Dict[str, Any]] = None


# =====================================================================
# 3. Password Hashing Utilities (Bcrypt)
# =====================================================================

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    import bcrypt
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against the stored bcrypt hash."""
    import bcrypt
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False



# =====================================================================
# 4. JWT Generation and Decoding
# =====================================================================

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generates a signed JWT access token containing user ID, Organization ID, and RBAC Role.
    """
    to_encode = data.copy()
    now_utc = datetime.now(timezone.utc)

    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now_utc,
        "nbf": now_utc
    })

    # Ensure critical payload types are strings
    if "id" in to_encode:
        to_encode["id"] = str(to_encode["id"])
    if "org_id" in to_encode:
        to_encode["org_id"] = str(to_encode["org_id"])
    if "role" in to_encode and hasattr(to_encode["role"], "value"):
        to_encode["role"] = to_encode["role"].value

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token. Raises HTTPException on expiration or tampering.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


# =====================================================================
# 5. FastAPI Security Dependencies
# =====================================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> CurrentUser:
    """
    FastAPI dependency that validates the Bearer JWT token from the Authorization header
    and returns a CurrentUser context.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header. Please authenticate with 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. 'Bearer' scheme is required.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_access_token(credentials.credentials)

    user_id = payload.get("id") or payload.get("sub")
    org_id = payload.get("org_id")
    role = payload.get("role")
    email = payload.get("email") or payload.get("sub")
    org_name = payload.get("org_name")

    if not user_id or not org_id or not role or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing required multi-tenant claims (id, org_id, role, email).",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        validated_role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid user role '{role}' in token payload."
        )

    return CurrentUser(
        id=str(user_id),
        org_id=str(org_id),
        email=str(email),
        role=validated_role,
        org_name=org_name
    )


def require_roles(allowed_roles: List[UserRole]):
    """
    Factory dependency for role-based access control (RBAC).
    Example usage:
        @router.post("/override", dependencies=[Depends(require_roles([UserRole.MANAGER, UserRole.MASTER_ADMIN]))])
    """
    async def role_checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            role_names = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access Denied: User with role '{current_user.role.value}' is unauthorized. "
                    f"Required role(s): {', '.join(role_names)}."
                )
            )
        return current_user

    return role_checker

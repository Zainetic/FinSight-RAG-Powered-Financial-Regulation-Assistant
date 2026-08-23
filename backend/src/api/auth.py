import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from src.core.limiter import limiter
from src.core.auth import (
    UserRole,
    CurrentUser,
    TokenResponse,
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_roles,
    set_auth_cookie,
    clear_auth_cookie
)
from src.core.database import (
    create_organization,
    get_organization_by_id,
    create_user,
    get_user_by_email,
    get_user_by_id,
    list_users_by_org
)
from src.core.ledger import create_genesis_block

router = APIRouter(prefix="/api/v1/auth", tags=["Multi-Tenant Authentication & RBAC"])


# =====================================================================
# Request & Response Schemas
# =====================================================================

class RegisterOrgRequest(BaseModel):
    org_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Name of the enterprise or fintech organization",
        example="Acme Fintech Global"
    )
    admin_email: EmailStr = Field(
        ...,
        description="Master Administrator's email address",
        example="admin@acmefintech.com"
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Secure password for the Master Admin account",
        example="P@ssw0rdSecure2026!"
    )


class RegisterOrgResponse(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    organization: Dict[str, Any]
    genesis_block: Optional[Dict[str, Any]] = None


class LoginRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="Registered user email",
        example="admin@acmefintech.com"
    )
    password: str = Field(
        ...,
        description="Account password",
        example="P@ssw0rdSecure2026!"
    )


class CreateUserRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="New user email to provision under current organization",
        example="developer1@acmefintech.com"
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Temporary or permanent password for the new user",
        example="DevPass2026!#"
    )
    role: UserRole = Field(
        ...,
        description="Role assignment: DEVELOPER or MANAGER",
        example=UserRole.DEVELOPER
    )


class UserProfileResponse(BaseModel):
    id: str
    org_id: str
    email: str
    role: str
    org_name: Optional[str] = None


# =====================================================================
# Authentication Endpoints (Rate-Limited & HttpOnly Cookie Protected)
# =====================================================================

@router.post(
    "/register-org",
    response_model=RegisterOrgResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Organization & Master Admin (Rate-Limited)",
    description=(
        "Provisions a new tenant organization, creates the initial MASTER_ADMIN user, "
        "generates the organization's initial cryptographic Genesis Block (#0), "
        "and sets a secure HttpOnly session cookie."
    )
)
@limiter.limit("10/minute")
async def register_organization(
    request: Request,
    response: Response,
    payload: RegisterOrgRequest
):
    # 1. Check if user already exists
    existing_user = get_user_by_email(str(payload.admin_email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{payload.admin_email}' already exists."
        )

    # 2. Create the Organization
    org = create_organization(name=payload.org_name)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create organization in database."
        )

    # 3. Hash password and create MASTER_ADMIN user
    hashed_pw = hash_password(payload.password)
    user = create_user(
        org_id=org["id"],
        email=str(payload.admin_email),
        hashed_password=hashed_pw,
        role=UserRole.MASTER_ADMIN.value
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create master admin user account."
        )

    # 4. Generate the Genesis Block for the organization's compliance ledger
    genesis_receipt = create_genesis_block(
        org_id=org["id"],
        org_name=payload.org_name,
        admin_email=str(payload.admin_email)
    )

    # 5. Issue JWT access token
    token_payload = {
        "id": user["id"],
        "sub": user["email"],
        "email": user["email"],
        "org_id": org["id"],
        "role": user["role"],
        "org_name": org["name"]
    }
    access_token = create_access_token(token_payload)

    # 6. Set secure HttpOnly session cookie (Rule 9)
    set_auth_cookie(response, access_token)

    return RegisterOrgResponse(
        message=f"Organization '{payload.org_name}' and MASTER_ADMIN registered successfully.",
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "org_id": user["org_id"]
        },
        organization=org,
        genesis_block=genesis_receipt
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login & JWT Issuance (Rate-Limited)",
    description=(
        "Authenticates user credentials, sets a secure HttpOnly session cookie, "
        "and returns a signed JWT containing user ID, Organization ID, and RBAC Role."
    )
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest
):
    # 1. Fetch user from PostgreSQL
    user = get_user_by_email(str(payload.email))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 2. Verify Bcrypt password hash
    if not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 3. Issue JWT Token with multi-tenant claims
    token_payload = {
        "id": user["id"],
        "sub": user["email"],
        "email": user["email"],
        "org_id": user["org_id"],
        "role": user["role"],
        "org_name": user.get("org_name")
    }
    access_token = create_access_token(token_payload)

    # 4. Set secure HttpOnly session cookie (Rule 9)
    set_auth_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=1440 * 60,  # in seconds
        user={
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "org_id": user["org_id"],
            "org_name": user.get("org_name")
        },
        organization={
            "id": user["org_id"],
            "name": user.get("org_name")
        }
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User Logout & Cookie Invalidation",
    description="Clears the HttpOnly session cookie from the client browser."
)
async def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "Successfully logged out and session cookie invalidated."}


@router.post(
    "/create-user",
    status_code=status.HTTP_201_CREATED,
    summary="Provision Organization Sub-User (MASTER_ADMIN only, Rate-Limited)",
    description="Allows a MASTER_ADMIN to provision new 'DEVELOPER' or 'MANAGER' accounts under their organization."
)
@limiter.limit("10/minute")
async def create_organization_user(
    request: Request,
    payload: CreateUserRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    # Strict RBAC Check: Only MASTER_ADMIN can provision users
    if current_user.role != UserRole.MASTER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Only MASTER_ADMIN can provision users for the organization."
        )

    # Prevent creating additional MASTER_ADMIN accounts through this endpoint
    if payload.role == UserRole.MASTER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot provision additional MASTER_ADMIN accounts via this endpoint."
        )

    # Check if email is already taken
    existing_user = get_user_by_email(str(payload.email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User account '{payload.email}' already exists."
        )

    # Hash password and create user under current_user's org_id
    hashed_pw = hash_password(payload.password)
    new_user = create_user(
        org_id=current_user.org_id,
        email=str(payload.email),
        hashed_password=hashed_pw,
        role=payload.role.value
    )

    if not new_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user in database."
        )

    return {
        "message": f"User '{payload.email}' successfully created with role '{payload.role.value}'.",
        "user": {
            "id": new_user["id"],
            "org_id": new_user["org_id"],
            "email": new_user["email"],
            "role": new_user["role"],
            "created_at": new_user["created_at"]
        }
    }


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get Current User Profile & Organization",
    description="Returns the profile and tenant context of the currently authenticated user."
)
async def get_my_profile(current_user: CurrentUser = Depends(get_current_user)):
    return UserProfileResponse(
        id=current_user.id,
        org_id=current_user.org_id,
        email=current_user.email,
        role=current_user.role.value,
        org_name=current_user.org_name
    )


@router.get(
    "/users",
    summary="List Organization Users (MASTER_ADMIN & MANAGER)",
    description="Lists all users belonging to the caller's organization with row-level data isolation."
)
async def list_org_users(
    current_user: CurrentUser = Depends(require_roles([UserRole.MASTER_ADMIN, UserRole.MANAGER]))
):
    users = list_users_by_org(current_user.org_id)
    return {
        "org_id": current_user.org_id,
        "total_users": len(users),
        "users": users
    }

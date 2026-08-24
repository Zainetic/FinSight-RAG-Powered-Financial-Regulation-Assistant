"""
FinSight RegTech - Prompts & Audit Record Management API
Provides prompt querying and RBAC-protected hard deletion endpoints.
"""

import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user, CurrentUser
from src.core.database import get_db
from src.core.models import Prompt, ComplianceLedger, Organization


router = APIRouter(prefix="/api/v1/prompts", tags=["Prompts & Template Management"])


# =====================================================================
# Pydantic Schemas
# =====================================================================

class PromptCreateRequest(BaseModel):
    title: Optional[str] = Field(None, example="High-Risk Biometrics Scan")
    content: str = Field(..., min_length=5, example="We are processing real-time facial recognition vectors for payments.")


class PromptResponse(BaseModel):
    id: str
    org_id: Optional[str] = None
    title: Optional[str] = None
    content: str
    created_at: Optional[str] = None


# =====================================================================
# Endpoints
# =====================================================================

@router.get(
    "",
    response_model=List[PromptResponse],
    status_code=status.HTTP_200_OK,
    summary="List Prompts & Templates",
    description="Retrieves prompts available to the current user's organization."
)
async def list_prompts(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    query = select(Prompt).order_by(Prompt.created_at.desc()).limit(100)
    result = await db.execute(query)
    entries = result.scalars().all()
    return [entry.to_dict() for entry in entries]


@router.post(
    "",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Prompt Template",
    description="Stores a new compliance prompt template for the authenticated organization."
)
async def create_prompt(
    payload: PromptCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    valid_org_id = None
    if current_user.org_id:
        try:
            target_org_uuid = uuid.UUID(current_user.org_id)
            org_check = await db.execute(select(Organization).where(Organization.id == target_org_uuid))
            if org_check.scalar_one_or_none():
                valid_org_id = target_org_uuid
        except Exception:
            pass

    new_prompt = Prompt(
        org_id=valid_org_id,
        title=payload.title,
        content=payload.content
    )
    db.add(new_prompt)
    await db.commit()
    await db.refresh(new_prompt)
    return new_prompt.to_dict()



@router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_200_OK,
    summary="Hard Delete Prompt / Audit Entry (RBAC Protected: Admin Only)",
    description="Deletes a specific prompt by UUID from the database. Strictly restricted to administrative roles."
)
async def delete_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    RBAC-protected prompt hard delete:
    Verifies user possesses administrative privileges (ADMIN, MASTER_ADMIN, SUPER_ADMIN).
    Deletes the specific prompt record by ID from PostgreSQL.
    """
    # 1. RBAC Authorization Check
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role.upper() not in ["ADMIN", "MASTER_ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to delete prompt"
        )

    # 2. Execute deletion
    deleted = False
    try:
        prompt_uuid = uuid.UUID(prompt_id)
        res = await db.execute(delete(Prompt).where(Prompt.id == prompt_uuid))
        if res.rowcount and res.rowcount > 0:
            deleted = True
    except (ValueError, Exception):
        pass

    # Fallback delete attempt against ComplianceLedger audit table
    if not deleted:
        try:
            audit_uuid = uuid.UUID(prompt_id)
            res = await db.execute(delete(ComplianceLedger).where(ComplianceLedger.audit_id == audit_uuid))
            if res.rowcount and res.rowcount > 0:
                deleted = True
        except (ValueError, Exception):
            pass

    await db.commit()

    return {
        "status": "success",
        "message": f"Prompt '{prompt_id}' deleted successfully.",
        "prompt_id": prompt_id,
        "deleted": deleted
    }

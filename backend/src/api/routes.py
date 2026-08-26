import os
import uuid
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.core.auth import (
    get_current_user,
    CurrentUser,
    UserRole
)
from src.core.rag import query_compliance_engine, astream_compliance_engine
from src.core.database import save_compliance_record
from src.core.ledger import (
    append_compliance_record,
    override_ledger_record,
    get_recent_ledger_blocks,
    verify_ledger_chain
)

router = APIRouter(tags=["Compliance & Ledger API"])


# =====================================================================
# 1. Pydantic Request & Response Schemas
# =====================================================================

class EvaluateRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=5,
        description="Architectural description or data flow to evaluate against regional regulations.",
        example="We are building a payment gateway that categorizes users based on biometric facial recognition."
    )
    jurisdictions: Optional[List[str]] = Field(
        default_factory=lambda: ["EU (AI Act, GDPR, PSD2)"],
        description="Target legal jurisdictions for multi-regional FAISS filtering",
        example=["EU (AI Act, GDPR, PSD2)", "US (CCPA/CPRA)"]
    )
    history: Optional[List[Dict[str, str]]] = Field(
        default=[],
        description="List of previous conversation turns formatted as [{'role': 'user'|'assistant', 'content': '...'}]"
    )
    mode: Optional[str] = Field(
        default="strict",
        description="Evaluation mode: 'strict' (3-state agentic auditing) or 'lenient' (scope-limited demo mode)"
    )


class EvaluateResponse(BaseModel):
    audit_id: str
    org_id: Optional[str] = None
    tx_hash: str
    prev_hash: str
    timestamp: str
    risk_category: str
    is_compliant: bool
    executive_summary_markdown: str
    citations: List[Dict[str, Any]]
    jurisdictions: List[str]
    ledger_receipt: Optional[Dict[str, Any]] = None


class OverrideRequest(BaseModel):
    audit_id: str = Field(
        ...,
        description="UUID of the original compliance audit record being disputed",
        example="3fa85f64-5717-4562-b3fc-2c963f66afa6"
    )
    justification: str = Field(
        ...,
        min_length=10,
        description="Legal justification or regulatory exemption for manual override",
        example="Biometric categorization is strictly localized on-device with zero cloud transmission under GDPR Art. 9(2)(a)."
    )


class OverrideResponse(BaseModel):
    audit_id: str
    original_audit_id: str
    org_id: Optional[str] = None
    timestamp: str
    model_provenance: str
    prev_hash: str
    tx_hash: str
    status: str
    justification: str


class WebhookPayload(BaseModel):
    repo_name: str = Field(
        ...,
        description="Repository identifier or URL from CI/CD pipeline",
        example="fintech-gateway/payments-service"
    )
    commit_hash: str = Field(
        ...,
        min_length=7,
        description="Git commit SHA being audited",
        example="9f8a3c2b1d0e4f5a6b7c8d9e0f1a2b3c4d5e6f7a"
    )
    architecture_changes: str = Field(
        ...,
        min_length=5,
        description="Proposed architectural specification or diff to audit against regional regulations",
        example="We are implementing a customer profiling feature using automated facial biometrics for credit scoring."
    )
    jurisdictions: Optional[List[str]] = Field(
        default=None,
        description="Optional list of target legal jurisdictions to filter (e.g. ['EU', 'UK', 'US'])",
        example=["EU", "UK"]
    )
    mode: Optional[str] = Field(
        default="strict",
        description="Evaluation mode for automated CI/CD pipeline ('strict' or 'lenient')"
    )


class WebhookScanResponse(BaseModel):
    audit_id: str
    is_compliant: bool
    tx_hash: str
    org_id: Optional[str] = None
    repo_name: Optional[str] = None
    commit_hash: Optional[str] = None
    risk_category: Optional[str] = None


# =====================================================================
# 2. Next.js Enterprise RESTful Streaming Routes
# =====================================================================

@router.post(
    "/api/v1/evaluate",
    summary="Evaluate Architectural Compliance (Streaming SSE, Authenticated)",
    description=(
        "Executes high-speed LangChain RAG streaming against FAISS with full multi-turn conversational memory, "
        "streams generated Markdown tokens in real-time via Server-Sent Events (SSE), "
        "and anchors the final compliance judgment into the tenant's immutable SHA-256 PostgreSQL ledger."
    )
)
async def evaluate_architecture(
    request: EvaluateRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    async def sse_generator():
        accumulated_tokens: List[str] = []
        citations: List[Dict[str, Any]] = []

        try:
            async for event in astream_compliance_engine(
                user_query=request.query.strip(),
                jurisdictions=request.jurisdictions,
                history=request.history,
                mode=request.mode or "strict"
            ):
                if event.get("type") == "start":
                    citations = event.get("citations", [])
                    yield f"data: {json.dumps(event)}\n\n"
                elif event.get("type") == "token":
                    raw_content = event.get("content", "")
                    if isinstance(raw_content, str):
                        content_str = raw_content
                    elif isinstance(raw_content, list):
                        content_str = "".join(str(item.get("text", item) if isinstance(item, dict) else item) for item in raw_content)
                    else:
                        content_str = str(raw_content)
                    accumulated_tokens.append(content_str)
                    yield f"data: {json.dumps({'type': 'token', 'content': content_str})}\n\n"

            full_summary_text = "".join(accumulated_tokens).strip()

            # Classify risk & compliance based on 3-state agentic matrix or generated report
            lower_summary = full_summary_text.lower()
            if "pending clarification" in lower_summary or "pending information" in lower_summary or "⏳ pending" in lower_summary or "### ❓ required clarifications" in lower_summary:
                risk_category = "Pending Clarification"
                is_compliant = False
            elif "compliant architecture" in lower_summary or "all applicable eu statutory requirements satisfied" in lower_summary or "compliant with controls" in lower_summary or "status: ✅" in lower_summary or "verified compliance controls" in lower_summary:
                risk_category = "Minimal Risk"
                is_compliant = True
            elif "prohibited" in lower_summary:
                risk_category = "Prohibited"
                is_compliant = False
            elif "critical vulnerabilities" in lower_summary or "mandatory remediation steps" in lower_summary:
                risk_category = "High-Risk"
                is_compliant = False
            elif "high-risk" in lower_summary or "high risk" in lower_summary:
                if "minimal risk" in lower_summary:
                    risk_category = "Minimal Risk"
                    is_compliant = True
                else:
                    risk_category = "High-Risk"
                    is_compliant = False
            elif "specific transparency" in lower_summary:
                risk_category = "Specific Transparency"
                is_compliant = True
            else:
                risk_category = "Minimal Risk"
                is_compliant = True

            audit_payload = {
                "risk_category": risk_category,
                "is_compliant": is_compliant,
                "executive_summary_markdown": full_summary_text,
                "citations": citations,
                "jurisdictions": request.jurisdictions or ["EU (AI Act, GDPR, PSD2)"],
                "org_id": current_user.org_id,
                "evaluated_by": current_user.email,
                "role": current_user.role.value,
                "mode": request.mode or "strict"
            }

            # Commit to immutable PostgreSQL SHA-256 ledger scoped to tenant's org_id
            model_provenance = f"STREAMING_API ({os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')})"
            ledger_receipt = append_compliance_record(
                user_query=request.query.strip(),
                payload=audit_payload,
                model_provenance=model_provenance,
                org_id=current_user.org_id
            )
            save_compliance_record(
                user_query=request.query.strip(),
                result_dict=audit_payload,
                org_id=current_user.org_id
            )

            done_event = {
                "type": "done",
                "audit_id": ledger_receipt["audit_id"] if ledger_receipt else str(uuid.uuid4()),
                "org_id": current_user.org_id,
                "tx_hash": ledger_receipt["tx_hash"] if ledger_receipt else "LOCAL_UNCOMMITTED",
                "prev_hash": ledger_receipt["prev_hash"] if ledger_receipt else "0" * 64,
                "timestamp": ledger_receipt["timestamp"] if ledger_receipt else "",
                "risk_category": risk_category,
                "is_compliant": is_compliant,
                "citations": citations,
                "jurisdictions": request.jurisdictions or ["EU (Default)"],
                "executive_summary_markdown": full_summary_text
            }
            yield f"data: {json.dumps(done_event)}\n\n"

        except Exception as e:
            error_event = {"type": "error", "detail": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post(
    "/api/v1/override",
    response_model=OverrideResponse,
    status_code=status.HTTP_200_OK,
    summary="Human-in-the-Loop Ledger Dispute Override (RBAC Protected)",
    description=(
        "Appends a new dispute override block linked to the latest transaction hash in the "
        "organization's immutable SHA-256 PostgreSQL ledger. "
        "Access is restricted to MANAGER and MASTER_ADMIN roles (DEVELOPER returns 403 Forbidden)."
    )
)
async def override_judgment(
    request: OverrideRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    # Strict RBAC Constraint: DEVELOPER role cannot perform manual overrides
    if current_user.role == UserRole.DEVELOPER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Users with DEVELOPER role are unauthorized to perform manual compliance overrides. Requires MANAGER or MASTER_ADMIN role."
        )

    try:
        override_receipt = override_ledger_record(
            audit_id=request.audit_id.strip(),
            justification=request.justification.strip(),
            org_id=current_user.org_id,
            operator_email=current_user.email
        )

        if not override_receipt:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to append dispute override block to organization ledger."
            )

        return OverrideResponse(
            audit_id=override_receipt["audit_id"],
            original_audit_id=override_receipt["original_audit_id"],
            org_id=override_receipt.get("org_id", current_user.org_id),
            timestamp=override_receipt["timestamp"],
            model_provenance=override_receipt["model_provenance"],
            prev_hash=override_receipt["prev_hash"],
            tx_hash=override_receipt["tx_hash"],
            status=override_receipt["status"],
            justification=override_receipt["justification"]
        )

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dispute override failed: {str(e)}"
        )


@router.get(
    "/api/v1/ledger",
    status_code=status.HTTP_200_OK,
    summary="Fetch Recent Organization Ledger Blocks (Authenticated)",
    description="Retrieves the most recent cryptographic ledger blocks from PostgreSQL for the user's organization with row-level data isolation."
)
async def get_ledger_blocks(
    limit: int = Query(default=10, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user)
):
    try:
        blocks = get_recent_ledger_blocks(org_id=current_user.org_id, limit=limit)
        is_valid, count, error_msg = verify_ledger_chain(org_id=current_user.org_id)
        return {
            "org_id": current_user.org_id,
            "total": len(blocks),
            "chain_valid": is_valid,
            "total_blocks_verified": count,
            "verification_error": error_msg,
            "blocks": blocks
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch ledger blocks: {str(e)}"
        )


# =====================================================================
# 3. CI/CD Automated Webhook Routes
# =====================================================================

@router.post(
    "/api/v1/scan-repo",
    response_model=WebhookScanResponse,
    responses={
        200: {"description": "Architecture is compliant. CI/CD build approved."},
        403: {"description": "Architecture violates regional regulations. CI/CD build blocked."},
        503: {"description": "Vector store or RAG engine unavailable."}
    },
    summary="CI/CD Automated Architecture Audit Webhook",
    description="GitHub Action webhook returning 200 for compliant architectures and 403 to block CI/CD if non-compliant."
)
async def scan_repo_webhook(
    payload: WebhookPayload,
    current_user: CurrentUser = Depends(get_current_user)
):
    try:
        result = query_compliance_engine(
            user_query=payload.architecture_changes.strip(),
            jurisdictions=payload.jurisdictions,
            history=[],
            mode=payload.mode or "strict"
        )

        audit_payload = {
            **result,
            "ci_cd_metadata": {
                "repo_name": payload.repo_name,
                "commit_hash": payload.commit_hash,
                "jurisdictions": payload.jurisdictions or ["EU (Default)"],
                "source": "GITHUB_ACTIONS_WEBHOOK",
                "org_id": current_user.org_id,
                "triggered_by": current_user.email,
                "mode": payload.mode or "strict"
            }
        }

        model_provenance = f"CI_CD_SCANNER ({os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')})"
        audit_query_label = f"[{payload.repo_name} @ {payload.commit_hash[:8]}] {payload.architecture_changes.strip()}"
        
        ledger_receipt = append_compliance_record(
            user_query=audit_query_label,
            payload=audit_payload,
            model_provenance=model_provenance,
            org_id=current_user.org_id
        )

        save_compliance_record(audit_query_label, audit_payload, org_id=current_user.org_id)

        audit_id = ledger_receipt["audit_id"] if ledger_receipt else "LOCAL_SESSION_ONLY"
        tx_hash = ledger_receipt["tx_hash"] if ledger_receipt else "NO_TX_HASH"
        is_compliant = bool(result.get("is_compliant", False))
        risk_category = result.get("risk_category", "Unclassified")

        response_body = {
            "audit_id": audit_id,
            "org_id": current_user.org_id,
            "is_compliant": is_compliant,
            "tx_hash": tx_hash,
            "repo_name": payload.repo_name,
            "commit_hash": payload.commit_hash,
            "risk_category": risk_category
        }

        if not is_compliant:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_body
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_body
        )

    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector store unavailable: {str(fnf)}"
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Automated compliance evaluation failed: {str(e)}"
        )

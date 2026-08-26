"""
FinSight RegTech - Automated Transaction Gatekeeper API
Machine-to-Machine Financial Compliance, Sanctions Screening, Zero-Trust PII Scrubbing,
FAISS Vector Store Regulatory Retrieval (AMLD6, TFR, PSD2, MiCA, DORA, GDPR), SHA-256 Audit Anchoring,
and Persistent PostgreSQL Transaction Ledger Storage.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user, CurrentUser
from src.core.database import get_db
from src.core.models import TransactionLedger
from src.schemas.transaction import TransactionPayload, TransactionEvaluationResult
from src.services.transactions import evaluate_transaction as run_transaction_evaluation


router = APIRouter(prefix="/api/v1/transactions", tags=["Automated Transaction Gatekeeper"])


# =====================================================================
# 1. Gatekeeper Evaluation Endpoint (with PostgreSQL Ledger Persistence)
# =====================================================================

@router.post(
    "/evaluate",
    response_model=TransactionEvaluationResult,
    status_code=status.HTTP_200_OK,
    summary="Automated Machine-to-Machine Financial Transaction Gatekeeper",
    description=(
        "Executes zero-trust PII scrubbing, queries the 615-article FAISS regulatory vector store (AMLD6, TFR, PSD2, MiCA), "
        "evaluates transfer compliance via Gemini Flash Native Structured Output, "
        "persists the immutable evaluation audit into PostgreSQL Transaction Ledger via SQLAlchemy, "
        "and generates a tamper-evident SHA-256 cryptographic audit digest."
    )
)
async def evaluate_transaction(
    payload: TransactionPayload,
    db: AsyncSession = Depends(get_db)
):
    try:
        # 1. Run dynamic FAISS RAG and structured LLM evaluation
        result = run_transaction_evaluation(payload)

        # 2. Persist Evaluation Audit into PostgreSQL Transaction Ledger
        now_utc = datetime.now(timezone.utc)
        risk_score_int = int(round(result.risk_score * 100)) if result.risk_score <= 1.0 else int(round(result.risk_score))
        
        # Format verdict for legacy database schema compatibility if needed
        db_verdict = "PASS" if result.verdict in ["APPROVED", "PASS"] else "FAIL"

        new_ledger_entry = TransactionLedger(
            transaction_id=result.transaction_id,
            payload_data=result.scrubbed_payload_sent_to_engine or {},
            verdict=db_verdict,
            risk_score=risk_score_int,
            rule_triggered=result.rule_triggered,
            legal_basis=result.legal_basis,
            sha256_hash=result.sha256_audit_hash or "LOCAL_HASH",
            timestamp=now_utc
        )
        db.add(new_ledger_entry)
        await db.commit()

        return result

    except Exception as e:
        print(f"[Transaction Gatekeeper Error] {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction evaluation failed: {str(e)}"
        )


# =====================================================================
# 2. Ledger History & Sandbox Purge Routes
# =====================================================================

@router.get(
    "/ledger",
    status_code=status.HTTP_200_OK,
    summary="Fetch Recent Transaction Ledger History",
    description="Retrieves the most recent 50 evaluated transaction records from the PostgreSQL ledger ordered by timestamp descending."
)
async def get_transaction_ledger(
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Selects the most recent entries from the transaction_ledger table,
    ordered by timestamp descending.
    """
    query = (
        select(TransactionLedger)
        .order_by(desc(TransactionLedger.timestamp))
        .limit(min(limit, 100))
    )
    result = await db.execute(query)
    entries = result.scalars().all()
    return [entry.to_dict() for entry in entries]


@router.delete(
    "/sandbox",
    status_code=status.HTTP_200_OK,
    summary="Purge Sandbox Transaction Ledger (RBAC Protected: Admin Only)",
    description="Deletes all simulated dummy transactions from the ledger database. Strictly restricted to administrative roles."
)
async def purge_sandbox_ledger(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    RBAC-protected sandbox purge:
    Verifies user possesses administrative privileges (ADMIN, MASTER_ADMIN, SUPER_ADMIN).
    Deletes all records from the transaction_ledger table.
    """
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role.upper() not in ["ADMIN", "MASTER_ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to purge sandbox"
        )

    result = await db.execute(delete(TransactionLedger))
    await db.commit()

    deleted_count = result.rowcount if hasattr(result, "rowcount") else 0

    return {
        "status": "success",
        "message": "Sandbox environment cleared.",
        "deleted_count": deleted_count
    }

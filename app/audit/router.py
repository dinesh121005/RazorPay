"""
Audit trail REST API router.

Exposes read endpoints to inspect the full audit trail of agent-proposed transactions,
their policy decisions, and payment rail outcomes.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.audit.models import AuditRecord
from app.audit.store import audit_store
from app.auth import verify_admin_key

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(verify_admin_key)]
)


@router.get(
    "",
    response_model=List[AuditRecord],
    status_code=status.HTTP_200_OK,
    summary="List audit records",
    description="Retrieve all transaction audit records, ordered newest first. Supports filtering by customer_id, decision, and payment_status."
)
def list_audit_records(
    customer_id: Optional[str] = Query(
        default=None,
        description="Filter records by customer ID (e.g. 'CUST001')"
    ),
    decision: Optional[str] = Query(
        default=None,
        description="Filter records by policy decision ('APPROVED' or 'REJECTED')"
    ),
    payment_status: Optional[str] = Query(
        default=None,
        description="Filter records by payment status ('created', 'failed', 'status_unknown', 'PENDING')"
    ),
) -> List[AuditRecord]:
    """
    List audit records with optional customer_id, decision, and payment_status filters.
    """
    return audit_store.list(customer_id=customer_id, decision=decision, payment_status=payment_status)


@router.get(
    "/{transaction_id}",
    response_model=AuditRecord,
    status_code=status.HTTP_200_OK,
    summary="Get single audit record",
    description="Retrieve a specific audit record by its transaction ID (UUID)."
)
def get_audit_record(transaction_id: str) -> AuditRecord:
    """
    Fetch a single audit record by transaction_id or return 404 if not found.
    """
    record = audit_store.get(transaction_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit record '{transaction_id}' not found"
        )
    return record

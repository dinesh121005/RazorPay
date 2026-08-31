"""
Agent commerce HTTP router.

Exposes POST /agent/purchase as a thin FastAPI wrapper around the core
purchase execution service in app.agent.service.
"""
from fastapi import APIRouter, status

from app.agent.service import (
    AgentPurchaseRequest,
    PurchaseResponse,
    execute_purchase,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/purchase",
    response_model=PurchaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Propose an agent purchase transaction",
    description="Thin HTTP endpoint delegating to the transport-agnostic purchase execution service."
)
def propose_purchase(payload: AgentPurchaseRequest) -> PurchaseResponse:
    """
    HTTP handler delegating to the core purchase execution service.
    """
    return execute_purchase(
        customer_id=payload.customer_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
    )

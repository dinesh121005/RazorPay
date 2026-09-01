"""
Agent commerce HTTP router.

Exposes POST /agent/purchase as a thin FastAPI wrapper around the core
purchase execution service in app.agent.service.
"""
from fastapi import APIRouter, HTTPException, status

from app.agent.service import (
    AgentPurchaseRequest,
    PurchaseResponse,
    execute_purchase,
)
from app.exceptions import (
    InsufficientStockError,
    InvalidPurchaseError,
    MandateNotFoundError,
    ProductNotFoundError,
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
    Maps domain exceptions to appropriate HTTP error status codes.
    """
    try:
        return execute_purchase(
            customer_id=payload.customer_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            idempotency_key=payload.idempotency_key,
        )
    except (ProductNotFoundError, MandateNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except InvalidPurchaseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

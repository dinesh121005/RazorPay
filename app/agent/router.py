from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.catalog.router import get_product
from app.payment import PaymentResult, create_order_for_approved
from app.policy.engine import evaluate
from app.policy.requests import PurchaseRequest
from app.policy.store import mandate_store

# Merchant identifier is derived per-product from product.merchant_id at runtime.
# No module-level merchant constant: the catalog is the authoritative source.

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentPurchaseRequest(BaseModel):
    """
    HTTP request payload for an AI shopping agent proposing a purchase.
    Separate from internal policy models to maintain clean API boundaries.
    """
    customer_id: str = Field(..., description="Unique customer identifier who authorized the mandate")
    product_id: str = Field(..., description="Unique identifier of the product being purchased")
    quantity: int = Field(default=1, ge=1, description="Quantity of items to purchase (must be >= 1)")


class PurchaseResponse(BaseModel):
    """
    HTTP response payload returned to the AI shopping agent with the policy engine verdict
    and, when approved, the Razorpay Test Mode order result.
    """
    decision: str = Field(..., description="Policy decision status: APPROVED or REJECTED")
    reason: str = Field(..., description="Human-readable explanation of the policy decision")
    product_id: str = Field(..., description="Identifier of the requested product")
    amount: float = Field(..., description="Total computed transaction amount (price × quantity) in INR (₹)")
    mandate_limit: float = Field(..., description="Customer's maximum transaction limit from mandate in INR (₹)")
    transaction_id: str = Field(..., description="Gateway-minted UUID for this proposal, used as Razorpay receipt")
    payment: Optional[PaymentResult] = Field(
        default=None,
        description="Razorpay order result when decision is APPROVED; None when REJECTED or payment is disabled."
    )


@router.post(
    "/purchase",
    response_model=PurchaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Propose an agent purchase transaction",
    description="Orchestrates product lookup, mandate retrieval, amount calculation, policy evaluation, and (on approval) Razorpay Test Mode order creation."
)
def propose_purchase(payload: AgentPurchaseRequest) -> PurchaseResponse:
    """
    Orchestrates purchase proposal evaluation:
    1. Look up product in catalog (returns 404 if not found).
    2. Look up customer mandate in store (returns 404 if not found).
    3. Compute total amount (price * quantity).
    4. Build PurchaseRequest for policy engine.
    5. Evaluate proposal against customer mandate (deterministic, no side effects).
    6. Mint a transaction_id for cross-system tracing.
    7. If APPROVED: create Razorpay Test Mode order via payment service.
       If REJECTED: skip Razorpay entirely — payment field is None.
    8. Return PurchaseResponse with decision + payment (HTTP 200 for both APPROVED and REJECTED).
    """
    # a. Catalog lookup (raises 404 if product not found)
    product = get_product(payload.product_id)

    # b. Mandate lookup (raises 404 if mandate not found)
    mandate = mandate_store.get_mandate(payload.customer_id)
    if mandate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mandate for customer '{payload.customer_id}' not found"
        )

    # c. Compute total transaction amount
    amount = product.price * payload.quantity

    # d. Build internal PurchaseRequest model
    purchase_request = PurchaseRequest(
        customer_id=payload.customer_id,
        product_id=product.id,
        category=product.category,
        amount=amount,
        merchant=product.merchant_id,
        quantity=payload.quantity
    )

    # e. Evaluate deterministically via Policy Engine
    decision = evaluate(purchase_request, mandate)

    # f. Mint a unique transaction ID for tracing across systems and the Razorpay dashboard
    transaction_id = str(uuid4())

    # g. Create Razorpay Test Mode order only on APPROVED — never touch payments on REJECTED
    if decision.status == "APPROVED":
        payment_result = create_order_for_approved(
            amount_inr=amount,
            receipt=transaction_id,
            customer_id=payload.customer_id,
            product_id=product.id,
        )
    else:
        payment_result = None

    # h. Return shaped PurchaseResponse (200 for both APPROVED and REJECTED)
    return PurchaseResponse(
        decision=decision.status,
        reason=decision.reason,
        product_id=product.id,
        amount=amount,
        mandate_limit=mandate.max_transaction_amount,
        transaction_id=transaction_id,
        payment=payment_result,
    )

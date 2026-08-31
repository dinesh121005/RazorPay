"""
Agent commerce service layer.

Provides transport-agnostic purchase execution logic shared across
both the FastAPI HTTP router and the stdio Model Context Protocol (MCP) server.
"""
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.audit import audit_store
from app.catalog.router import get_product
from app.payment import PaymentResult, create_order_for_approved
from app.policy.engine import evaluate
from app.policy.requests import PurchaseRequest
from app.policy.store import mandate_store


class AgentPurchaseRequest(BaseModel):
    """
    Request payload for an AI shopping agent proposing a purchase.
    """
    customer_id: str = Field(..., description="Unique customer identifier who authorized the mandate")
    product_id: str = Field(..., description="Unique identifier of the product being purchased")
    quantity: int = Field(default=1, ge=1, description="Quantity of items to purchase (must be >= 1)")


class PurchaseResponse(BaseModel):
    """
    Response payload returned with the policy engine verdict and payment outcome.
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


def execute_purchase(
    customer_id: str,
    product_id: str,
    quantity: int = 1,
) -> PurchaseResponse:
    """
    Executes the full purchase proposal orchestration:
    1. Look up product in catalog (raises 404 if not found).
    2. Look up customer mandate in store (raises 404 if not found).
    3. Compute total amount (price * quantity).
    4. Build PurchaseRequest for policy engine.
    5. Evaluate proposal against customer mandate (deterministic, no side effects).
    6. Mint a unique transaction_id for cross-system tracing.
    7. Phase A Audit: Record proposal, verdict, and reasoning in SQLite audit store.
    8. If APPROVED: create Razorpay Test Mode order and record Phase B audit outcome.
       If REJECTED: skip Razorpay entirely (payment is None).
    9. Return shaped PurchaseResponse.
    """
    # a. Catalog lookup (raises 404 if product not found)
    product = get_product(product_id)

    # b. Mandate lookup (raises 404 if mandate not found)
    mandate = mandate_store.get_mandate(customer_id)
    if mandate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mandate for customer '{customer_id}' not found"
        )

    # c. Compute total transaction amount
    amount = product.price * quantity

    # d. Build internal PurchaseRequest model
    purchase_request = PurchaseRequest(
        customer_id=customer_id,
        product_id=product.id,
        category=product.category,
        amount=amount,
        merchant=product.merchant_id,
        quantity=quantity,
    )

    # e. Evaluate deterministically via Policy Engine
    decision = evaluate(purchase_request, mandate)

    # f. Mint a unique transaction ID for tracing across systems and the Razorpay dashboard
    transaction_id = str(uuid4())

    # g. Phase A Audit: Record the evaluated proposal and rule decision
    audit_store.write_proposal(
        transaction_id=transaction_id,
        customer_id=customer_id,
        product_id=product.id,
        merchant_id=product.merchant_id,
        quantity=quantity,
        amount=amount,
        decision=decision.status,
        decision_reason=decision.reason,
    )

    # h. Create Razorpay Test Mode order only on APPROVED — never touch payments on REJECTED
    if decision.status == "APPROVED":
        payment_result = create_order_for_approved(
            amount_inr=amount,
            receipt=transaction_id,
            customer_id=customer_id,
            product_id=product.id,
        )
        # Phase B Audit: Update the row with the payment outcome
        audit_store.update_payment_outcome(
            transaction_id=transaction_id,
            payment_status=payment_result.status,
            razorpay_order_id=payment_result.razorpay_order_id,
        )
    else:
        payment_result = None

    # i. Return shaped PurchaseResponse
    return PurchaseResponse(
        decision=decision.status,
        reason=decision.reason,
        product_id=product.id,
        amount=amount,
        mandate_limit=mandate.max_transaction_amount,
        transaction_id=transaction_id,
        payment=payment_result,
    )

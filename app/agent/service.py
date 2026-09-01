"""
Agent commerce service layer.

Provides transport-agnostic purchase execution logic shared across
both the FastAPI HTTP router and the stdio Model Context Protocol (MCP) server.
"""
import hashlib
import sqlite3
import time
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.audit import AuditRecord, audit_store
from app.catalog.service import get_product
from app.exceptions import (
    InsufficientStockError,
    InvalidPurchaseError,
    MandateNotFoundError,
    ProductNotFoundError,
)
from app.payment import PaymentResult, create_order_for_approved
from app.policy.engine import evaluate
from app.policy.requests import PurchaseRequest
from app.policy.store import mandate_store


def generate_bucketed_idempotency_key(
    customer_id: str,
    product_id: str,
    quantity: int,
    timestamp: Optional[float] = None,
) -> str:
    """
    Generate a deterministic idempotency key bucketed to the nearest 60-second window.
    Format: sha256 of (customer_id:product_id:quantity:floor(current_unix_timestamp / 60))
    """
    ts = time.time() if timestamp is None else timestamp
    bucket = int(ts // 60)
    raw = f"{customer_id.strip()}:{product_id.strip()}:{quantity}:{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _build_replayed_response(record: AuditRecord) -> "PurchaseResponse":
    """
    Constructs a PurchaseResponse from an existing audit trail record.
    Ensures consistent shape for cached/replayed responses.
    """
    mandate = mandate_store.get_mandate(record.customer_id)
    limit = mandate.max_transaction_amount if mandate else record.amount
    payment = None
    if record.payment_status is not None:
        payment = PaymentResult(
            status=record.payment_status,
            razorpay_order_id=record.razorpay_order_id,
        )
    return PurchaseResponse(
        decision=record.decision,
        reason=record.decision_reason,
        product_id=record.product_id,
        amount=record.amount,
        mandate_limit=limit,
        transaction_id=record.transaction_id,
        payment=payment,
        idempotency_key=record.idempotency_key,
    )


class AgentPurchaseRequest(BaseModel):
    """
    Request payload for an AI shopping agent proposing a purchase.
    """
    customer_id: str = Field(..., description="Unique customer identifier who authorized the mandate")
    product_id: str = Field(..., description="Unique identifier of the product being purchased")
    quantity: int = Field(default=1, ge=1, description="Quantity of items to purchase (must be >= 1)")
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional client-supplied idempotency key to prevent duplicate orders on retry. Auto-generated if omitted."
    )


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
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Client-supplied or bucket-generated idempotency key associated with this transaction"
    )


def execute_purchase(
    customer_id: str,
    product_id: str,
    quantity: int = 1,
    idempotency_key: Optional[str] = None,
) -> PurchaseResponse:
    """
    Executes the full purchase proposal orchestration:
    1. Validate input parameters (quantity >= 1 and integer).
    2. Resolve mandatory idempotency_key (override if provided, else deterministic 60s bucket).
    3. Check idempotency replay: return cached record if idempotency_key was already processed.
    4. Look up product in catalog (raises ProductNotFoundError if not found).
    5. Check inventory stock (raises InsufficientStockError if quantity > stock).
    6. Look up customer mandate in store (raises MandateNotFoundError if not found).
    7. Compute total amount (price * quantity).
    8. Build PurchaseRequest for policy engine.
    9. Evaluate proposal against customer mandate (deterministic, no side effects).
    10. Mint a unique transaction_id for cross-system tracing.
    11. Phase A Audit: Record proposal, verdict, and reasoning in SQLite audit store.
        Catches sqlite3.IntegrityError to resolve concurrent race conditions gracefully.
    12. If APPROVED: create Razorpay Test Mode order and record Phase B audit outcome.
        If REJECTED: skip Razorpay entirely (payment is None).
    13. Return shaped PurchaseResponse.
    """
    # 1. Transport-agnostic input validation
    if not isinstance(quantity, int) or quantity < 1:
        raise InvalidPurchaseError(f"Quantity must be a positive integer (>= 1), got {quantity}")

    # 2. Mandatory internal idempotency key resolution
    if not idempotency_key or not idempotency_key.strip():
        idempotency_key = generate_bucketed_idempotency_key(customer_id, product_id, quantity)
    else:
        idempotency_key = idempotency_key.strip()

    # 3. Idempotency replay check
    existing_record = audit_store.get_by_idempotency_key(idempotency_key)
    if existing_record is not None:
        return _build_replayed_response(existing_record)

    # 4. Catalog lookup (raises ProductNotFoundError if not found)
    product = get_product(product_id)

    # 5. Inventory stock availability check
    if quantity > product.stock:
        raise InsufficientStockError(
            product_id=product.id,
            requested=quantity,
            available=product.stock,
        )

    # 6. Mandate lookup (raises MandateNotFoundError if not found)
    mandate = mandate_store.get_mandate(customer_id)
    if mandate is None:
        raise MandateNotFoundError(customer_id)

    # 7. Compute total transaction amount
    amount = product.price * quantity

    # 8. Build internal PurchaseRequest model
    purchase_request = PurchaseRequest(
        customer_id=customer_id,
        product_id=product.id,
        category=product.category,
        amount=amount,
        merchant=product.merchant_id,
        quantity=quantity,
    )

    # 9. Evaluate deterministically via Policy Engine
    decision = evaluate(purchase_request, mandate)

    # 10. Mint a unique transaction ID for tracing across systems and the Razorpay dashboard
    transaction_id = str(uuid4())

    # 11. Phase A Audit: Record the evaluated proposal and rule decision
    try:
        audit_store.write_proposal(
            transaction_id=transaction_id,
            customer_id=customer_id,
            product_id=product.id,
            merchant_id=product.merchant_id,
            quantity=quantity,
            amount=amount,
            decision=decision.status,
            decision_reason=decision.reason,
            idempotency_key=idempotency_key,
        )
    except (sqlite3.IntegrityError, sqlite3.OperationalError):
        # Race condition & lock contention safeguard: check if concurrent request committed winning record
        existing_record = audit_store.get_by_idempotency_key(idempotency_key)
        if existing_record is not None:
            return _build_replayed_response(existing_record)
        raise

    # 12. Create Razorpay Test Mode order only on APPROVED — never touch payments on REJECTED
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

    # 13. Return shaped PurchaseResponse
    return PurchaseResponse(
        decision=decision.status,
        reason=decision.reason,
        product_id=product.id,
        amount=amount,
        mandate_limit=mandate.max_transaction_amount,
        transaction_id=transaction_id,
        payment=payment_result,
        idempotency_key=idempotency_key,
    )

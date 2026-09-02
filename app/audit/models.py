"""
Audit trail models for ai-buyer-gateway.

Defines the Pydantic schema for queryable audit records capturing the entire lifecycle
of an agent purchase proposal: proposal details, policy decision verdict & reasoning,
and downstream payment execution status.
"""
from typing import Optional
from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """
    Structured record representing a single transaction proposal evaluated by the gateway.
    Stored permanently in SQLite for explainability, compliance, and auditing.
    """
    transaction_id: str = Field(
        ...,
        description="Unique gateway-minted UUID for the transaction proposal, matching Razorpay receipt"
    )
    timestamp: str = Field(
        ...,
        description="UTC ISO 8601 timestamp when the proposal was evaluated"
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier requesting the purchase"
    )
    product_id: str = Field(
        ...,
        description="Product identifier requested from the catalog"
    )
    merchant_id: str = Field(
        ...,
        description="Merchant identifier associated with the product"
    )
    quantity: int = Field(
        ...,
        description="Quantity requested (>= 1)"
    )
    amount: float = Field(
        ...,
        description="Total computed transaction amount in INR (price * quantity)"
    )
    decision: str = Field(
        ...,
        description="Policy engine evaluation outcome: 'APPROVED' or 'REJECTED'"
    )
    decision_reason: str = Field(
        ...,
        description="Specific human-readable explanation of why the policy rule approved or rejected the proposal"
    )
    payment_status: Optional[str] = Field(
        default=None,
        description="Downstream payment status: 'PENDING' (approved, awaiting payment), 'created' (successful order), 'failed' (SDK/network error), 'status_unknown' (provider omitted status), or None (when rejected)"
    )
    razorpay_order_id: Optional[str] = Field(
        default=None,
        description="Razorpay Order ID (e.g. 'order_ABC123') when payment order creation succeeded, else None"
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional client-supplied idempotency key for replay prevention"
    )
    prev_hash: Optional[str] = Field(
        default="GENESIS",
        description="SHA-256 cryptographic hash of the preceding audit record"
    )
    record_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 cryptographic hash of this audit record payload and prev_hash"
    )


class AuditEvent(BaseModel):
    """
    Append-only immutable event block in the cryptographic SHA-256 hash chain.
    Guarantees non-repudiation and tamper evidence across all transaction lifecycle events.
    """
    id: Optional[int] = Field(default=None, description="Sequential auto-incrementing ledger position")
    event_id: str = Field(..., description="Unique UUID for this event")
    transaction_id: str = Field(..., description="Gateway transaction UUID this event pertains to")
    event_type: str = Field(..., description="Event type: PROPOSAL_EVALUATED, HUMAN_CONFIRMED, ORDER_CREATED, PAYMENT_CAPTURED, PAYMENT_FAILED")
    timestamp: str = Field(..., description="UTC ISO 8601 timestamp")
    payload_json: str = Field(..., description="Deterministic JSON representation of the event payload")
    prev_hash: str = Field(default="GENESIS", description="SHA-256 hash of the immediately preceding event")
    event_hash: str = Field(..., description="SHA-256 hash of this event block")



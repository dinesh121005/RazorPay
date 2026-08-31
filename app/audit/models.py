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
        description="Downstream payment status: 'created' (successful order), 'failed' (SDK/network error), or None (when rejected)"
    )
    razorpay_order_id: Optional[str] = Field(
        default=None,
        description="Razorpay Order ID (e.g. 'order_ABC123') when payment order creation succeeded, else None"
    )

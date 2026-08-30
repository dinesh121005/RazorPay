from typing import Literal, Optional
from pydantic import BaseModel, Field


class PaymentResult(BaseModel):
    """
    Result of a Razorpay Test Mode order creation attempt.
    Returned alongside the PolicyDecision in POST /agent/purchase when decision is APPROVED.
    A 'failed' status means the Razorpay API call did not succeed — the policy decision itself
    is unaffected; an agent failure does not reverse an authorization.
    """
    status: Literal["created", "failed"] = Field(
        ...,
        description="'created' if the Razorpay order was successfully placed; 'failed' if the SDK call raised an exception."
    )
    razorpay_order_id: Optional[str] = Field(
        default=None,
        description="Razorpay order ID (e.g. 'order_ABC123') returned on successful creation."
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error message when status is 'failed'. None when status is 'created'."
    )

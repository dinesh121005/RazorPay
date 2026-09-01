from typing import Literal, Optional
from pydantic import BaseModel, Field


class PaymentResult(BaseModel):
    """
    Result of a Razorpay Test Mode order creation attempt.
    Returned alongside the PolicyDecision in POST /agent/purchase when decision is APPROVED.
    A 'failed' status means the Razorpay API call raised an exception.
    A 'status_unknown' status means the API response was missing the status field.
    """
    status: Literal["created", "failed", "status_unknown"] = Field(
        ...,
        description="'created' if the Razorpay order was successfully placed; 'failed' if an exception was raised; 'status_unknown' if provider response omitted status."
    )
    razorpay_order_id: Optional[str] = Field(
        default=None,
        description="Razorpay order ID (e.g. 'order_ABC123') returned on creation attempt."
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error message when status is 'failed' or 'status_unknown'. None when status is 'created'."
    )

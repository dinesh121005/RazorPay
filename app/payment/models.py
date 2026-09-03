from typing import Literal, Optional
from pydantic import BaseModel, Field


class PaymentResult(BaseModel):
    """
    Result of a Razorpay Test Mode order creation or auto-pay settlement attempt.
    Returned alongside the PolicyDecision in POST /agent/purchase.
    """
    status: Literal["created", "captured", "failed", "status_unknown"] = Field(
        ...,
        description="'captured' if settled via auto-debit; 'created' if Razorpay order/link was placed; 'failed' if an error occurred; 'status_unknown' if provider response omitted status."
    )
    razorpay_order_id: Optional[str] = Field(
        default=None,
        description="Razorpay order ID (e.g. 'order_ABC123') returned on creation attempt."
    )
    payment_url: Optional[str] = Field(
        default=None,
        description="Razorpay hosted payment link URL (e.g. 'https://rzp.io/i/xxxx') for customer self-checkout."
    )
    qr_code_url: Optional[str] = Field(
        default=None,
        description="Dynamic UPI QR Code image URL for instant mobile checkout."
    )
    payment_method: Optional[str] = Field(
        default=None,
        description="Payment execution rail used: 'auto_debit' (mandate wallet), 'razorpay_order', or 'razorpay_link'."
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error message when status is 'failed' or 'status_unknown'. None when status is 'created' or 'captured'."
    )

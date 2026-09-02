from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class RuleViolated(str, Enum):
    """
    Enumeration of specific rules that can be violated during policy evaluation.
    """
    CUSTOMER_MISMATCH = "CUSTOMER_MISMATCH"
    MANDATE_EXPIRED = "MANDATE_EXPIRED"
    MERCHANT_NOT_ALLOWED = "MERCHANT_NOT_ALLOWED"
    CATEGORY_NOT_ALLOWED = "CATEGORY_NOT_ALLOWED"
    AMOUNT_EXCEEDS_LIMIT = "AMOUNT_EXCEEDS_LIMIT"
    DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"


class PurchaseRequest(BaseModel):
    """
    Representation of a purchase proposed by an AI Buyer Agent.

    Note: The `amount` field is pre-computed by the caller as `price × quantity`.
    This model and the policy engine never recalculate it.
    """
    customer_id: str = Field(..., description="Customer on whose behalf the agent is acting")
    product_id: str = Field(..., description="ID of the product being purchased")
    category: str = Field(..., description="Category of the product being purchased")
    amount: float = Field(..., gt=0, description="Pre-computed total amount (price × quantity) in INR (₹)")
    merchant: str = Field(..., description="Merchant identifier where the purchase is being proposed")
    quantity: int = Field(default=1, ge=1, description="Quantity of items being purchased")


class PolicyDecision(BaseModel):
    """
    Evaluation verdict returned by the Policy / Mandate Engine.
    """
    status: Literal["APPROVED", "REJECTED"] = Field(..., description="Mandate decision status: APPROVED or REJECTED")
    reason: str = Field(..., description="Specific, human-readable explanation citing actual values involved")
    rule_violated: Optional[RuleViolated] = Field(default=None, description="Rule that was violated; must be None when APPROVED")

from app.policy.mandate import Mandate
from app.policy.requests import PolicyDecision, PurchaseRequest, RuleViolated


def evaluate(purchase_request: PurchaseRequest, mandate: Mandate) -> PolicyDecision:
    """
    Pure, deterministic evaluation function that checks a proposed purchase request against a customer's mandate.

    Rules are evaluated in strict fail-fast sequential order:
      1. customer_id match -> CUSTOMER_MISMATCH
      2. mandate.is_expired() is False -> MANDATE_EXPIRED
      3. merchant in allowed_merchants (case-insensitive, trimmed) -> MERCHANT_NOT_ALLOWED
      4. category in allowed_categories (case-insensitive, trimmed) -> CATEGORY_NOT_ALLOWED
      5. amount <= max_transaction_amount (inclusive boundary) -> AMOUNT_EXCEEDS_LIMIT

    Returns on the very first violated check. On approval, rule_violated is None.
    """
    # 1. Customer ID match
    if purchase_request.customer_id != mandate.customer_id:
        return PolicyDecision(
            status="REJECTED",
            reason=f"Customer ID '{purchase_request.customer_id}' does not match mandate customer '{mandate.customer_id}'",
            rule_violated=RuleViolated.CUSTOMER_MISMATCH
        )

    # 2. Mandate expiry check
    if mandate.is_expired():
        expiry_str = mandate.expires_at.isoformat() if mandate.expires_at else "unknown"
        return PolicyDecision(
            status="REJECTED",
            reason=f"Mandate for customer '{mandate.customer_id}' has expired (expired at {expiry_str})",
            rule_violated=RuleViolated.MANDATE_EXPIRED
        )

    # 3. Merchant authorization check (case-insensitive, trimmed)
    allowed_merchants_normalized = [m.strip().lower() for m in mandate.allowed_merchants]
    if purchase_request.merchant.strip().lower() not in allowed_merchants_normalized:
        return PolicyDecision(
            status="REJECTED",
            reason=f"Merchant '{purchase_request.merchant}' is not authorized in customer mandate (allowed: {mandate.allowed_merchants})",
            rule_violated=RuleViolated.MERCHANT_NOT_ALLOWED
        )

    # 4. Category authorization check (case-insensitive, trimmed)
    allowed_categories_normalized = [c.strip().lower() for c in mandate.allowed_categories]
    if purchase_request.category.strip().lower() not in allowed_categories_normalized:
        return PolicyDecision(
            status="REJECTED",
            reason=f"Product category '{purchase_request.category}' is not authorized in customer mandate (allowed: {mandate.allowed_categories})",
            rule_violated=RuleViolated.CATEGORY_NOT_ALLOWED
        )

    # 5. Transaction amount boundary check (inclusive)
    if purchase_request.amount > mandate.max_transaction_amount:
        return PolicyDecision(
            status="REJECTED",
            reason=(
                f"Transaction amount ₹{purchase_request.amount:.2f} exceeds "
                f"maximum mandate limit of ₹{mandate.max_transaction_amount:.2f}"
            ),
            rule_violated=RuleViolated.AMOUNT_EXCEEDS_LIMIT
        )

    # All checks passed successfully
    return PolicyDecision(
        status="APPROVED",
        reason=(
            f"Transaction amount ₹{purchase_request.amount:.2f} is within "
            f"mandate limit of ₹{mandate.max_transaction_amount:.2f} and meets all policy criteria"
        ),
        rule_violated=None
    )

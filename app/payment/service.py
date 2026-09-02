"""
Payment service — orchestrates Razorpay Test Mode order creation and payment lifecycle.

Payment Rails Architecture (2-Phase Execution):
1. Phase 1 (Order Creation): Upon policy mandate approval and human confirmation,
   creates an official Razorpay Order via `razorpay_client.create_order()` with
   `payment_capture=1` and traceability notes. Returns `status="created"` with `razorpay_order_id`.
2. Phase 2 (Payment Confirmation & Webhook Settlement): Server-to-server webhook callbacks
   (`POST /payment/webhook`) and client signature verification (`POST /payment/verify`)
   verify HMAC-SHA256 signatures, transitioning transaction state to `status="captured"`.

Responsibilities:
- Convert rupees (catalog/policy domain) → paise (Razorpay domain).
- Build the Razorpay `notes` payload for cross-system dashboard traceability.
- Call razorpay_client.create_order() and map the result to a PaymentResult.
- Isolate all SDK exceptions: a payment rail failure never corrupts the PolicyDecision.
"""
import logging
from app.payment import razorpay_client
from app.payment.models import PaymentResult

logger = logging.getLogger("gateway.payment")

# Paise per rupee — Razorpay Orders API requires integer paise.
_PAISE_PER_RUPEE = 100


def _rupees_to_paise(amount_inr: float) -> int:
    """
    Convert a rupee amount (float) to an integer paise value.
    Uses round() before int() to avoid floating-point truncation errors
    (e.g. 1499.0 * 100 = 149900 exactly, but guard against edge cases).
    """
    return int(round(amount_inr * _PAISE_PER_RUPEE))


def create_order_for_approved(
    amount_inr: float,
    receipt: str,
    customer_id: str,
    product_id: str,
) -> PaymentResult:
    """
    Create a Razorpay Test Mode order for a policy-approved purchase proposal.

    This function is called ONLY when PolicyDecision.status == "APPROVED".
    The caller (app/agent/service.py) is responsible for the conditional guard;
    this function has no awareness of the policy decision itself.

    Args:
        amount_inr:  Transaction amount in Indian Rupees (from the catalog/policy domain).
        receipt:     The gateway's transaction_id — used as Razorpay receipt for tracing.
        customer_id: Mandate customer identifier, stored in Razorpay order notes.
        product_id:  Catalog product identifier, stored in Razorpay order notes.

    Returns:
        PaymentResult(status="created", razorpay_order_id=...) on success.
        PaymentResult(status="failed", error=...) if the SDK call raises any exception.
        The policy decision is unaffected in either case.
    """
    amount_paise = _rupees_to_paise(amount_inr)
    notes = {
        "customer_id": customer_id,
        "product_id": product_id,
        "transaction_id": receipt,
        "gateway": "ai-buyer-gateway",
    }

    try:
        response = razorpay_client.create_order(
            amount_paise=amount_paise,
            receipt=receipt,
            notes=notes,
        )
        if not isinstance(response, dict) or "status" not in response or not response.get("status"):
            logger.warning(
                "Razorpay response missing 'status' field for receipt %s: %s",
                receipt,
                response,
            )
            return PaymentResult(
                status="status_unknown",
                razorpay_order_id=response.get("id") if isinstance(response, dict) else None,
                error="Razorpay response missing 'status' field",
            )

        return PaymentResult(
            status=response["status"],
            razorpay_order_id=response.get("id"),
        )
    except Exception as exc:  # noqa: BLE001 — intentional broad catch; SDK can raise many types
        logger.warning(
            "Razorpay order creation failed for transaction receipt %s: %s",
            receipt,
            exc,
            exc_info=True,
        )
        return PaymentResult(
            status="failed",
            error=str(exc),
        )

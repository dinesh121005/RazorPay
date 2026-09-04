"""
Payment service — orchestrates Razorpay Test Mode order creation, payment links,
dynamic UPI QR codes, and pre-authorized auto-debit settlements.
"""
import logging
import os
from typing import Optional
from app.payment import razorpay_client
from app.payment.models import PaymentResult
from app.wallet.store import wallet_store

logger = logging.getLogger("gateway.payment")

# Paise per rupee — Razorpay Orders & Payment Links API require integer paise.
_PAISE_PER_RUPEE = 100


def _rupees_to_paise(amount_inr: float) -> int:
    """
    Convert a rupee amount (float) to an integer paise value.
    """
    return int(round(amount_inr * _PAISE_PER_RUPEE))


def execute_auto_debit(
    amount_inr: float,
    receipt: str,
    customer_id: str,
    product_id: str,
) -> PaymentResult:
    """
    Executes autonomous auto-debit from customer's pre-authorized mandate balance.
    When successful, marks the transaction immediately as 'captured' (PAID).
    """
    success, remaining_bal, msg = wallet_store.debit(customer_id, amount_inr)
    if not success:
        logger.warning(
            "Auto-debit failed for customer %s (amount ₹%.2f): %s. Escalating to payment link.",
            customer_id,
            amount_inr,
            msg,
        )
        return PaymentResult(
            status="failed",
            payment_method="auto_debit",
            error=msg,
        )

    logger.info(
        "Auto-debit successful for customer %s: ₹%.2f debited. Remaining balance: ₹%.2f",
        customer_id,
        amount_inr,
        remaining_bal,
    )
    return PaymentResult(
        status="captured",
        payment_method="auto_debit",
        razorpay_order_id=f"auto_{receipt[:16]}",
    )


import hashlib
import hmac
import urllib.parse


def generate_checkout_token(receipt: str, amount_inr: float, customer_id: str) -> str:
    """
    Generates an HMAC-SHA256 authorization signature for hosted checkout links.
    Guarantees that frontend checkout requests cannot tamper with amount, receipt, or customer_id.
    """
    secret = os.environ.get("JWT_SECRET", "dev-secret-key-change-in-production")
    data = f"{receipt}|{amount_inr:.2f}|{customer_id}"
    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_checkout_token(token: str, receipt: str, amount_inr: float, customer_id: str) -> bool:
    """
    Verifies that a checkout token matches the server-computed signature.
    """
    if not token:
        return False
    expected = generate_checkout_token(receipt, amount_inr, customer_id)
    return hmac.compare_digest(token, expected)


def create_payment_link_for_manual(
    amount_inr: float,
    receipt: str,
    customer_id: str,
    product_id: str,
    product_name: Optional[str] = None,
) -> PaymentResult:
    """
    Creates a dedicated Hosted Checkout Link / Razorpay Payment Link and dynamic UPI QR Code for user self-checkout
    when a purchase is not approved for auto-debit by policy mandate.
    Includes a cryptographically signed checkout_token to prevent tampering on checkout.
    """
    name = product_name or product_id
    base_url = os.environ.get("BASE_URL", "https://razorpay-c454.onrender.com").rstrip("/")
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")

    # Attempt real Razorpay Payment Link API call if credentials are configured
    if key_id and key_secret and razorpay_client.razorpay is not None:
        try:
            amount_paise = _rupees_to_paise(amount_inr)
            pl_data = razorpay_client.create_payment_link(
                amount_paise=amount_paise,
                receipt=receipt,
                description=f"Escalation Checkout: {name}",
                notes={"customer_id": customer_id, "product_id": product_id},
            )
            short_url = pl_data.get("short_url") or pl_data.get("url")
            pl_id = pl_data.get("id", f"plink_{receipt.replace('-', '')[:16]}")
            if short_url:
                qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(short_url)}"
                return PaymentResult(
                    status="created",
                    razorpay_order_id=pl_id,
                    payment_url=short_url,
                    qr_code_url=qr_code_url,
                    payment_method="razorpay_link",
                )
        except Exception as e:
            logger.warning("Razorpay Payment Link API call failed, falling back to gateway checkout: %s", e)

    # Sandbox / Local hosted checkout fallback with tamper-proof token signature
    effective_key = key_id or "rzp_test_51tPkUG58N7Lkg"
    checkout_token = generate_checkout_token(receipt, amount_inr, customer_id)

    query = urllib.parse.urlencode({
        "order_id": f"order_{receipt.replace('-', '')[:16]}",
        "amount": f"{amount_inr:.2f}",
        "product": name,
        "key": effective_key,
        "customer": customer_id,
        "receipt": receipt,
        "token": checkout_token,
    })
    checkout_url = f"{base_url}/checkout?{query}"
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(checkout_url)}"

    return PaymentResult(
        status="created",
        razorpay_order_id=f"order_{receipt.replace('-', '')[:16]}",
        payment_url=checkout_url,
        qr_code_url=qr_code_url,
        payment_method="gateway_escalation_checkout",
    )


def create_order_for_approved(
    amount_inr: float,
    receipt: str,
    customer_id: str,
    product_id: str,
) -> PaymentResult:
    """
    Create a Razorpay Test Mode order.
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

        order_id = response.get("id")
        short_url = f"https://rzp.io/i/{order_id}"
        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={short_url}"
        return PaymentResult(
            status=response["status"],
            razorpay_order_id=order_id,
            payment_url=short_url,
            qr_code_url=qr_code_url,
            payment_method="razorpay_order",
        )
    except Exception as exc:
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

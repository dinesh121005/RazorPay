"""
Razorpay SDK wrapper for the ai-buyer-gateway.

This is the ONLY file in the project that imports the `razorpay` package.
All other modules interact with Razorpay exclusively through the functions here.

Design: lazy singleton — the SDK client is not instantiated at import time,
so `pytest` collection works without RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET set.
The real client is created on the first call to get_client().
"""
import logging
import os
import razorpay

_logger = logging.getLogger("gateway.payment.client")
_client = None


def get_client() -> razorpay.Client:
    """
    Return the module-level Razorpay client singleton, creating it on first call.
    Reads RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET from environment variables.
    Raises KeyError if either variable is absent (fail loudly rather than silently
    using empty credentials that would produce confusing Razorpay auth errors).
    """
    global _client
    if _client is None:
        key_id = os.environ["RAZORPAY_KEY_ID"]
        key_secret = os.environ["RAZORPAY_KEY_SECRET"]
        _client = razorpay.Client(auth=(key_id, key_secret))
    return _client


def create_order(amount_paise: int, receipt: str, notes: dict) -> dict:
    """
    Create a Razorpay order in Test Mode.

    Args:
        amount_paise: Transaction amount in paise (100 paise = ₹1). Must be a positive integer.
        receipt:      Unique receipt string (the gateway's transaction_id) for cross-system tracing.
        notes:        Arbitrary key-value metadata attached to the order in the Razorpay dashboard.

    Returns:
        The raw order dict returned by the Razorpay Orders API, containing at minimum:
        {"id": "order_ABC...", "amount": ..., "currency": "INR", "status": "created", ...}

    Raises:
        Any exception from the razorpay SDK or underlying HTTP layer — callers are responsible
        for catching and handling these (see payment.service).
    """
    client = get_client()
    return client.order.create(data={
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,
        "notes": notes,
    })


def verify_webhook_signature(body_bytes: bytes, signature: str, webhook_secret: str) -> bool:
    """
    Verifies Razorpay webhook payload signature using HMAC-SHA256.
    """
    import hashlib
    import hmac
    if not signature or not webhook_secret:
        return False
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Verifies Razorpay client-side payment signature for checkout verification.
    """
    client = get_client()
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
        return True
    except Exception:
        return False


"""
Live Test Mode Checkout Integration Test for Razorpay.

Demonstrates the real, live Razorpay Test Mode checkout lifecycle without mocks:
1. Create real order via live Razorpay Test API (rzp_test_* credentials).
2. Verify order returns status 'created' and an authentic Razorpay order ID.
3. Simulate customer checkout completion by generating a cryptographically valid HMAC-SHA256 signature using the live test secret.
4. Verify the signature on server rails via /payment/verify.
5. Confirm that the transaction state in the audit ledger transitions from 'created' to 'captured' and decision to 'APPROVED'.
"""
import hashlib
import hmac
import os
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from uuid import uuid4

load_dotenv()

from app.audit import audit_store
from app.main import app
import app.payment.razorpay_client as rzp_client_module

client = TestClient(app)

_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")

# Marked as integration test since it hits external Razorpay Test API
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _KEY_ID or not _KEY_SECRET or "test" not in _KEY_ID.lower(),
        reason="Live Razorpay Test credentials (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET) not configured.",
    ),
]


def test_live_razorpay_checkout_lifecycle():
    """
    End-to-End Live Checkout Lifecycle:
    create order (real API) -> customer signature -> verified signature -> captured audit record.
    """
    # Ensure client singleton uses live credentials
    rzp_client_module._client = None

    tx_id = f"tx-live-{uuid4().hex[:10]}"
    amount = 500.0

    # 1. Write initial proposal into audit ledger
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST_LIVE_TEST",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=amount,
        decision="REJECTED",
        decision_reason="Exceeds mandate limit - escalated to live checkout",
        idempotency_key=f"idemp-{tx_id}",
    )

    # 2. Call /payment/create-order (UNMOCKED live Razorpay Test API call)
    resp = client.post(
        "/payment/create-order",
        json={
            "receipt": tx_id,
            "amount": amount,
            "customer_id": "CUST_LIVE_TEST",
            "product_name": "Ultra HD Monitor 4K",
        },
    )
    assert resp.status_code == 200, f"Order creation failed: {resp.text}"
    order_data = resp.json()

    real_order_id = order_data["order_id"]
    assert real_order_id.startswith("order_"), f"Expected order_*, got {real_order_id}"
    assert order_data["amount"] == amount
    assert order_data["currency"] == "INR"

    # Verify audit record updated to 'created'
    record = audit_store.get(tx_id)
    assert record is not None
    assert record.payment_status == "created"
    assert record.razorpay_order_id == real_order_id

    # 3. Simulate customer checkout completion: compute valid HMAC-SHA256 signature
    fake_payment_id = f"pay_live_{uuid4().hex[:12]}"
    signature_payload = f"{real_order_id}|{fake_payment_id}".encode("utf-8")
    valid_signature = hmac.new(
        _KEY_SECRET.encode("utf-8"),
        signature_payload,
        hashlib.sha256,
    ).hexdigest()

    # 4. Verify payment via /payment/verify
    verify_resp = client.post(
        "/payment/verify",
        json={
            "razorpay_order_id": real_order_id,
            "razorpay_payment_id": fake_payment_id,
            "razorpay_signature": valid_signature,
            "receipt": tx_id,
        },
    )
    assert verify_resp.status_code == 200, f"Verification failed: {verify_resp.text}"
    verify_data = verify_resp.json()
    assert verify_data["verified"] is True
    assert verify_data["razorpay_order_id"] == real_order_id

    # 5. Assert authoritative transition to 'captured' in audit ledger
    final_record = audit_store.get(tx_id)
    assert final_record.payment_status == "captured"
    assert final_record.decision == "APPROVED"
    assert "Escalated purchase completed via hosted checkout" in final_record.decision_reason

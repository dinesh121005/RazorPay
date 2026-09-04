"""
Security and Integrity Tests for Razorpay Hosted Checkout.

Verifies:
1. Gating /payment/create-order against unauthorized or unknown receipts (HTTP 404).
2. Anti-tampering protection rejecting client-modified amounts (HTTP 400).
3. Rejection of order creation on already settled/paid transactions (HTTP 400).
4. Secure checkout token generation and verification.
5. Strict cryptographic payment signature verification rejection on invalid signature (HTTP 400).
6. Truthful state transition to 'captured' and 'APPROVED' upon valid signature verification and webhook.
"""
import hashlib
import hmac
import json
import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.audit import audit_store
from app.main import app
from app.payment.service import generate_checkout_token, verify_checkout_token

client = TestClient(app)
_ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-secret-key"}
_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_SecureTest123",
    "entity": "order",
    "amount": 499900,
    "currency": "INR",
    "status": "created",
    "receipt": "tx-secure-001",
}


def test_create_order_unauthorized_receipt_rejected():
    """
    Ensures that calling /payment/create-order with an unknown receipt or random receipt
    without an authorized server-side record is strictly rejected with HTTP 404.
    Prevents arbitrary order minting against merchant's Razorpay account.
    """
    resp = client.post(
        "/payment/create-order",
        json={
            "receipt": "arbitrary-unknown-uuid-999",
            "amount": 100.0,
            "product_name": "Hack Attempt",
            "customer_id": "ATTACKER",
        },
    )
    assert resp.status_code == 404
    assert "Unauthorized checkout intent" in resp.json()["detail"]


def test_create_order_empty_receipt_rejected():
    """
    Ensures that calling /payment/create-order with an empty receipt returns HTTP 400.
    """
    resp = client.post(
        "/payment/create-order",
        json={
            "receipt": "",
            "amount": 100.0,
        },
    )
    assert resp.status_code == 400


def test_create_order_amount_tamper_rejected():
    """
    Ensures that if an authorized transaction was recorded for ₹4,999.00,
    a caller attempting to mint an order for ₹1.00 is rejected with HTTP 400 (anti-tamper guard).
    """
    tx_id = "tx-tamper-check-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="REJECTED",
        decision_reason="Exceeds mandate limit",
        idempotency_key="idemp-tamper-001",
    )

    resp = client.post(
        "/payment/create-order",
        json={
            "receipt": tx_id,
            "amount": 1.0,  # Tampered amount
            "customer_id": "CUST001",
        },
    )
    assert resp.status_code == 400
    assert "Amount mismatch" in resp.json()["detail"]


def test_create_order_authorized_success():
    """
    Verifies that an authorized out-of-mandate transaction can mint a real Razorpay Order
    with the server-authorized amount.
    """
    tx_id = "tx-authorized-order-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="REJECTED",
        decision_reason="Exceeds mandate cap",
        idempotency_key="idemp-auth-001",
    )

    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        resp = client.post(
            "/payment/create-order",
            json={
                "receipt": tx_id,
                "amount": 4999.0,
                "customer_id": "CUST001",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["order_id"] == "order_SecureTest123"
    assert data["amount"] == 4999.0
    assert data["currency"] == "INR"

    # Verify audit ledger updated with order ID
    record = audit_store.get(tx_id)
    assert record.razorpay_order_id == "order_SecureTest123"
    assert record.payment_status == "created"


def test_create_order_already_settled_rejected():
    """
    Verifies that attempting to mint another order for an already settled transaction
    is rejected with HTTP 400.
    """
    tx_id = "tx-already-settled-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="APPROVED",
        decision_reason="Settled",
        idempotency_key="idemp-settled-001",
    )
    audit_store.update_payment_outcome(
        transaction_id=tx_id,
        payment_status="captured",
        razorpay_order_id="order_Settled999",
    )

    resp = client.post(
        "/payment/create-order",
        json={
            "receipt": tx_id,
            "amount": 4999.0,
            "customer_id": "CUST001",
        },
    )
    assert resp.status_code == 400
    assert "already been paid and settled" in resp.json()["detail"]


def test_create_order_razorpay_failure_returns_502():
    """
    Verifies that /payment/create-order returns HTTP 502 Bad Gateway and logs payment_status='failed'
    when Razorpay order creation fails.
    """
    tx_id = "tx-fail-order-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="APPROVED",
        decision_reason="Testing failure",
        idempotency_key="idemp-fail-order-001",
    )

    with patch("app.payment.razorpay_client.create_order", side_effect=Exception("Razorpay API Timeout")):
        resp = client.post(
            "/payment/create-order",
            json={
                "receipt": tx_id,
                "amount": 4999.0,
                "customer_id": "CUST001",
            },
        )
    assert resp.status_code == 502
    assert "Razorpay order creation failed" in resp.json()["detail"]

    # Verify audit record marked payment_status = failed
    record = audit_store.get(tx_id)
    assert record.payment_status == "failed"


def test_checkout_token_cryptographic_verification():
    """
    Tests that HMAC-SHA256 checkout tokens are tamper-proof.
    """
    receipt = "tx-token-test-123"
    amount = 1499.0
    cust = "CUST001"

    token = generate_checkout_token(receipt, amount, cust)
    assert len(token) == 64  # SHA256 hex digest

    # Valid token verification
    assert verify_checkout_token(token, receipt, amount, cust) is True

    # Tampered amount rejects token
    assert verify_checkout_token(token, receipt, 100.0, cust) is False

    # Tampered customer rejects token
    assert verify_checkout_token(token, receipt, amount, "ATTACKER") is False


def test_payment_verify_invalid_signature_rejected():
    """
    Tests that /payment/verify strictly rejects tampered or invalid Razorpay signatures with HTTP 400.
    """
    resp = client.post(
        "/payment/verify",
        json={
            "razorpay_order_id": "order_Fake123",
            "razorpay_payment_id": "pay_Fake456",
            "razorpay_signature": "invalid_tampered_signature_hex",
            "receipt": "some-receipt",
        },
    )
    assert resp.status_code == 400
    assert "Invalid Razorpay payment signature" in resp.json()["detail"]


def test_payment_verify_valid_signature_transitions_to_captured():
    """
    Tests that a valid HMAC signature successfully transitions the transaction to captured
    and updates decision to APPROVED.
    """
    tx_id = "tx-verify-success-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="REJECTED",
        decision_reason="Exceeds mandate limit",
        idempotency_key="idemp-verify-001",
    )

    order_id = "order_RealTest789"
    payment_id = "pay_RealTest101"
    secret = os.environ.get("RAZORPAY_KEY_SECRET", "dev-razorpay-secret")
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    valid_sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    resp = client.post(
        "/payment/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
            "receipt": tx_id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is True

    # Check that audit record transitioned to captured and APPROVED
    record = audit_store.get(tx_id)
    assert record.payment_status == "captured"
    assert record.decision == "APPROVED"
    assert "Escalated purchase completed via hosted checkout signature verification" in record.decision_reason


def test_payment_verify_mismatched_order_id_rejected():
    """
    Integrity test: /payment/verify rejects payment completion if submitted razorpay_order_id
    does not match the razorpay_order_id bound to the receipt in audit ledger.
    """
    tx_id = "tx-mismatch-order-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="REJECTED",
        decision_reason="Exceeds mandate limit",
        idempotency_key="idemp-mismatch-001",
    )
    audit_store.update_payment_outcome(
        transaction_id=tx_id,
        payment_status="created",
        razorpay_order_id="order_Bound123",
    )

    other_order_id = "order_Attacker999"
    payment_id = "pay_Attacker999"
    secret = os.environ.get("RAZORPAY_KEY_SECRET", "dev-razorpay-secret")
    msg = f"{other_order_id}|{payment_id}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    resp = client.post(
        "/payment/verify",
        json={
            "razorpay_order_id": other_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sig,
            "receipt": tx_id,
        },
    )
    assert resp.status_code == 400
    assert "Payment integrity violation" in resp.json()["detail"]


def test_simulate_webhook_settles_transaction():
    """
    Tests the sandbox test endpoint /payment/simulate-webhook.
    """
    tx_id = "tx-sim-webhook-001"
    audit_store.write_proposal(
        transaction_id=tx_id,
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="REJECTED",
        decision_reason="Exceeds mandate limit",
        idempotency_key="idemp-sim-001",
    )

    # Unauthenticated call must be rejected
    unauth_resp = client.post(
        "/payment/simulate-webhook",
        json={"transaction_id": tx_id, "event": "payment.captured"},
    )
    assert unauth_resp.status_code == 401

    # Authenticated call succeeds
    resp = client.post(
        "/payment/simulate-webhook",
        json={"transaction_id": tx_id, "event": "payment.captured"},
        headers=_ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["payment_status"] == "captured"
    assert data["settled"] is True

    record = audit_store.get(tx_id)
    assert record.payment_status == "captured"
    assert record.decision == "APPROVED"

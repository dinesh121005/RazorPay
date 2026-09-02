"""
Integration tests for Phase 5 — Razorpay Test Mode payment integration.

All tests in this file mock `app.payment.razorpay_client.create_order` so that
no real network calls are made in the default pytest run. The one exception is
`test_real_razorpay_api`, which is marked `@pytest.mark.integration` and skipped
by default — run it manually with real Test Mode keys to verify pre-demo.

Mock target: `app.payment.razorpay_client.create_order`
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.payment.service import _rupees_to_paise, create_order_for_approved

client = TestClient(app)

_ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-secret-key"}

# ─── Mock target path ──────────────────────────────────────────────────────────
_CREATE_ORDER = "app.payment.razorpay_client.create_order"

# ─── Canonical fake Razorpay order response ────────────────────────────────────
_FAKE_ORDER = {
    "id": "order_TestFakeABC123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "some-txn-id",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Rupee → Paise conversion (pure unit tests, no HTTP)
# ══════════════════════════════════════════════════════════════════════════════

def test_rupee_to_paise_kb001():
    """KB001: ₹1,499.00 → 149900 paise (exact integer)."""
    assert _rupees_to_paise(1499.0) == 149900


def test_rupee_to_paise_fd001():
    """FD001: ₹349.00 → 34900 paise."""
    assert _rupees_to_paise(349.0) == 34900


def test_rupee_to_paise_mn001():
    """MN001: ₹4,999.00 → 499900 paise (over-limit product, conversion still correct)."""
    assert _rupees_to_paise(4999.0) == 499900


def test_rupee_to_paise_rounding():
    """Floating-point edge: ₹10.005 rounds to 1001 paise, not truncated to 1000."""
    assert _rupees_to_paise(10.005) == 1001


# ══════════════════════════════════════════════════════════════════════════════
# 2. APPROVED purchase → Razorpay order created
# ══════════════════════════════════════════════════════════════════════════════

def test_approved_purchase_creates_order():
    """
    CUST001 + FD001 (₹349, within mandate and < ₹500 threshold) → APPROVED.
    Razorpay order created; response includes PaymentResult with status='created'
    and a non-empty razorpay_order_id.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "FD001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0

    # Payment field present and successful
    assert data["payment"] is not None
    assert data["payment"]["status"] == "created"
    assert data["payment"]["razorpay_order_id"] == "order_TestFakeABC123"
    assert data["payment"]["error"] is None

    # Razorpay was called exactly once
    mock_create.assert_called_once()


def test_approved_contains_transaction_id():
    """Response for APPROVED purchase includes a non-empty transaction_id UUID."""
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "FD001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    data = response.json()
    assert data["decision"] == "APPROVED"
    txn_id = data.get("transaction_id")
    assert txn_id is not None
    assert isinstance(txn_id, str)
    assert len(txn_id) == 36  # UUID4 format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx


def test_transaction_id_passed_as_receipt():
    """
    The gateway's transaction_id is forwarded to Razorpay as the `receipt` field,
    enabling cross-system tracing in the Razorpay dashboard.
    """
    captured = {}

    def capture_create_order(amount_paise, receipt, notes):
        captured["receipt"] = receipt
        captured["amount_paise"] = amount_paise
        return _FAKE_ORDER

    with patch(_CREATE_ORDER, side_effect=capture_create_order):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "FD001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    data = response.json()
    assert data["decision"] == "APPROVED"
    # The receipt Razorpay received must equal the transaction_id in the response
    assert captured["receipt"] == data["transaction_id"]
    # Amount must be in paise: ₹349 → 34900
    assert captured["amount_paise"] == 34900


# ══════════════════════════════════════════════════════════════════════════════
# 3. REJECTED purchase → Razorpay never called
# ══════════════════════════════════════════════════════════════════════════════

def test_rejected_purchase_no_payment_call():
    """
    CUST001 + MN001 (₹4,999 > ₹2,000 mandate) → REJECTED.
    Razorpay must never be called; payment field in response is None.
    """
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "MN001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )
        mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["payment"] is None


def test_rejected_response_has_null_payment():
    """Rejected response serializes payment as JSON null, not an absent key."""
    with patch(_CREATE_ORDER):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "MN001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    data = response.json()
    assert data["decision"] == "REJECTED"
    assert "payment" in data           # field is present in the JSON
    assert data["payment"] is None     # and its value is null


def test_rejected_contains_transaction_id():
    """Even rejected purchases receive a transaction_id for audit trail purposes."""
    with patch(_CREATE_ORDER):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "MN001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    data = response.json()
    assert data["decision"] == "REJECTED"
    txn_id = data.get("transaction_id")
    assert txn_id is not None
    assert len(txn_id) == 36


# ══════════════════════════════════════════════════════════════════════════════
# 4. Razorpay SDK failure → isolated, decision is PAYMENT_FAILED
# ══════════════════════════════════════════════════════════════════════════════

def test_razorpay_failure_returns_failed_payment():
    """
    When the Razorpay SDK raises an exception on autonomous execution, the response is HTTP 200.
    The final decision is PAYMENT_FAILED and payment.status == 'failed'.
    """
    with patch(_CREATE_ORDER, side_effect=Exception("Razorpay network timeout")):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "FD001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "PAYMENT_FAILED"
    assert data["payment"] is not None
    assert data["payment"]["status"] == "failed"
    assert data["payment"]["razorpay_order_id"] is None
    assert "Razorpay network timeout" in data["payment"]["error"]


def test_service_create_order_success():
    """
    create_order_for_approved() returns PaymentResult(status='created') on SDK success.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        result = create_order_for_approved(
            amount_inr=1499.0,
            receipt="txn-unit-test-001",
            customer_id="CUST001",
            product_id="KB001",
        )

    assert result.status == "created"
    assert result.razorpay_order_id == "order_TestFakeABC123"
    assert result.error is None


def test_service_create_order_failure_isolation():
    """
    create_order_for_approved() catches all SDK exceptions and returns
    PaymentResult(status='failed') — never re-raises.
    """
    with patch(_CREATE_ORDER, side_effect=ValueError("bad response")):
        result = create_order_for_approved(
            amount_inr=1499.0,
            receipt="txn-unit-test-002",
            customer_id="CUST001",
            product_id="KB001",
        )

    assert result.status == "failed"
    assert result.razorpay_order_id is None
    assert "bad response" in result.error


def test_service_create_order_missing_status_sets_status_unknown():
    """
    create_order_for_approved() sets status='status_unknown' and populates error
    when the Razorpay response dictionary omits the 'status' key.
    """
    with patch(_CREATE_ORDER, return_value={"id": "order_NoStatus123", "amount": 149900}):
        result = create_order_for_approved(
            amount_inr=1499.0,
            receipt="txn-unit-test-003",
            customer_id="CUST001",
            product_id="KB001",
        )

    assert result.status == "status_unknown"
    assert result.razorpay_order_id == "order_NoStatus123"
    assert "missing 'status' field" in result.error


def test_razorpay_missing_status_recorded_in_purchase_response():
    """
    HTTP /agent/purchase endpoint correctly surfaces status_unknown when
    Razorpay response is missing the 'status' key.
    """
    with patch(_CREATE_ORDER, return_value={"id": "order_NoStatus456"}):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "FD001",
                "quantity": 1,
            },
            headers=_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["payment"] is not None
    assert data["payment"]["status"] == "status_unknown"
    assert data["payment"]["razorpay_order_id"] == "order_NoStatus456"
    assert "missing 'status' field" in data["payment"]["error"]


# ══════════════════════════════════════════════════════════════════════════════
# 5. Razorpay Webhook & Payment Verification Endpoints
# ══════════════════════════════════════════════════════════════════════════════

def test_webhook_payment_captured_valid_signature():
    """
    POST /payment/webhook with valid HMAC-SHA256 signature updates transaction to 'captured'.
    """
    import hmac
    import hashlib
    import json

    secret = "dev-webhook-secret"
    payload_dict = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_WebHookTest123",
                    "order_id": "order_TestFakeABC123",
                    "amount": 34900,
                    "status": "captured",
                    "notes": {
                        "transaction_id": "txn-test-webhook-capture-001"
                    }
                }
            }
        }
    }
    body_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    # Pre-seed proposal
    from app.audit import audit_store
    audit_store.write_proposal(
        transaction_id="txn-test-webhook-capture-001",
        customer_id="CUST001",
        product_id="FD001",
        merchant_id="MERCH_FOOD",
        quantity=1,
        amount=349.0,
        decision="APPROVED",
        decision_reason="Pre-seed for webhook test",
    )

    resp = client.post(
        "/payment/webhook",
        content=body_bytes,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "ok"
    assert res_data["processed"] is True

    record = audit_store.get("txn-test-webhook-capture-001")
    assert record is not None
    assert record.payment_status == "captured"


def test_webhook_invalid_signature_returns_400():
    """
    POST /payment/webhook with invalid or missing signature returns 400 Bad Request.
    """
    resp = client.post(
        "/payment/webhook",
        content=b'{"event": "payment.captured"}',
        headers={"X-Razorpay-Signature": "invalid-sig", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_webhook_duplicate_event_deduplication():
    """
    POST /payment/webhook with the same event ID returns deduplicated 200 OK without re-processing.
    """
    import hmac
    import hashlib
    import json

    secret = "dev-webhook-secret"
    payload_dict = {
        "event_id": "evt_dedup_test_999",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_WebHookDedup999",
                    "order_id": "order_Dedup999",
                    "amount": 34900,
                    "status": "captured",
                    "notes": {
                        "transaction_id": "txn-dedup-001"
                    }
                }
            }
        }
    }
    from app.audit import audit_store
    audit_store.write_proposal(
        transaction_id="txn-dedup-001",
        customer_id="CUST001",
        product_id="FD001",
        merchant_id="MERCH_FOOD",
        quantity=1,
        amount=349.0,
        decision="APPROVED",
        decision_reason="Pre-seed for dedup test",
    )

    body_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    # First delivery
    resp1 = client.post(
        "/payment/webhook",
        content=body_bytes,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json", "X-Razorpay-Event-Id": "evt_dedup_test_999"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["deduplicated"] is False

    # Second delivery (Duplicate retry from Razorpay)
    resp2 = client.post(
        "/payment/webhook",
        content=body_bytes,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json", "X-Razorpay-Event-Id": "evt_dedup_test_999"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["deduplicated"] is True


def test_webhook_payment_failed_restores_inventory():
    """
    POST /payment/webhook on payment.failed automatically restores decremented stock for the product.
    """
    import hmac
    import hashlib
    import json
    from app.catalog.service import get_product
    from app.audit import audit_store

    secret = "dev-webhook-secret"
    prod = get_product("HK001")
    initial_stock = prod.stock

    # Pre-seed transaction
    audit_store.write_proposal(
        transaction_id="txn-fail-restore-001",
        customer_id="CUST001",
        product_id="HK001",
        merchant_id="MERCH_ELEC",
        quantity=2,
        amount=998.0,
        decision="APPROVED",
        decision_reason="Pre-seed for failure restore test",
    )
    # Simulate stock decrement
    prod.stock -= 2
    assert prod.stock == initial_stock - 2

    payload_dict = {
        "event_id": "evt_fail_test_777",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_WebHookFail777",
                    "order_id": "order_Fail777",
                    "amount": 99800,
                    "status": "failed",
                    "notes": {
                        "transaction_id": "txn-fail-restore-001"
                    }
                }
            }
        }
    }
    body_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    resp = client.post(
        "/payment/webhook",
        content=body_bytes,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json", "X-Razorpay-Event-Id": "evt_fail_test_777"},
    )
    assert resp.status_code == 200
    assert resp.json()["event"] == "payment.failed"

    # Inventory must be restored by +2
    assert prod.stock == initial_stock

    # Audit status must be failed
    record = audit_store.get("txn-fail-restore-001")
    assert record.payment_status == "failed"



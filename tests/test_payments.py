"""
Integration tests for Phase 5 — Razorpay Test Mode payment integration.

All tests in this file mock `app.payment.razorpay_client.create_order` so that
no real network calls are made in the default pytest run. The one exception is
`test_real_razorpay_api`, which is marked `@pytest.mark.integration` and skipped
by default — run it manually with real Test Mode keys to verify pre-demo.

Mock target: `app.payment.razorpay_client.create_order`
  This is the single entry point to the Razorpay SDK in the project; mocking it
  here intercepts all real HTTP calls while exercising the full router → service
  → client path.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.payment.service import _rupees_to_paise, create_order_for_approved

client = TestClient(app)

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
    CUST001 + KB001 (₹1,499, within mandate) → APPROVED.
    Razorpay order created; response includes PaymentResult with status='created'
    and a non-empty razorpay_order_id.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "KB001"
    assert data["amount"] == 1499.0

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
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

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
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

    data = response.json()
    assert data["decision"] == "APPROVED"
    # The receipt Razorpay received must equal the transaction_id in the response
    assert captured["receipt"] == data["transaction_id"]
    # Amount must be in paise: ₹1,499 → 149900
    assert captured["amount_paise"] == 149900


# ══════════════════════════════════════════════════════════════════════════════
# 3. REJECTED purchase → Razorpay never called
# ══════════════════════════════════════════════════════════════════════════════

def test_rejected_purchase_no_payment_call():
    """
    CUST001 + MN001 (₹4,999 > ₹2,000 mandate) → REJECTED.
    Razorpay must never be called; payment field in response is None.
    """
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "MN001",
            "quantity": 1,
        })
        mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["payment"] is None


def test_rejected_response_has_null_payment():
    """Rejected response serializes payment as JSON null, not an absent key."""
    with patch(_CREATE_ORDER):
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "MN001",
            "quantity": 1,
        })

    data = response.json()
    assert data["decision"] == "REJECTED"
    assert "payment" in data           # field is present in the JSON
    assert data["payment"] is None     # and its value is null


def test_rejected_contains_transaction_id():
    """Even rejected purchases receive a transaction_id for audit trail purposes."""
    with patch(_CREATE_ORDER):
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "MN001",
            "quantity": 1,
        })

    data = response.json()
    assert data["decision"] == "REJECTED"
    txn_id = data.get("transaction_id")
    assert txn_id is not None
    assert len(txn_id) == 36


# ══════════════════════════════════════════════════════════════════════════════
# 4. Razorpay SDK failure → isolated, decision unchanged
# ══════════════════════════════════════════════════════════════════════════════

def test_razorpay_failure_returns_failed_payment():
    """
    When the Razorpay SDK raises an exception, the response is still HTTP 200.
    The PolicyDecision is APPROVED (unchanged); payment.status == 'failed'
    with a non-empty error message.
    """
    with patch(_CREATE_ORDER, side_effect=Exception("Razorpay network timeout")):
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

    assert response.status_code == 200
    data = response.json()

    # Policy decision is still APPROVED — the SDK failure doesn't reverse authorization
    assert data["decision"] == "APPROVED"

    # Payment reflects the failure, not the policy
    assert data["payment"] is not None
    assert data["payment"]["status"] == "failed"
    assert data["payment"]["razorpay_order_id"] is None
    assert "Razorpay network timeout" in data["payment"]["error"]


def test_razorpay_failure_decision_reason_unchanged():
    """
    SDK failure must not mutate the reason string from the policy engine.
    The reason must still describe the policy outcome, not the payment failure.
    """
    with patch(_CREATE_ORDER, side_effect=RuntimeError("SDK error")):
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

    data = response.json()
    assert data["decision"] == "APPROVED"
    # Policy engine reason — not SDK error text
    assert "within mandate limit" in data["reason"]
    assert "SDK error" not in data["reason"]


# ══════════════════════════════════════════════════════════════════════════════
# 5. Service-level unit tests (bypass HTTP, test service directly)
# ══════════════════════════════════════════════════════════════════════════════

def test_service_create_order_success():
    """
    create_order_for_approved() returns PaymentResult(status='created') on SDK success.
    Verifies the service correctly extracts razorpay_order_id from the response dict.
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


# ══════════════════════════════════════════════════════════════════════════════
# 6. Integration test (skipped by default — requires real Test Mode keys)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
def test_real_razorpay_api():
    """
    Hits the real Razorpay Test Mode API. Requires RAZORPAY_KEY_ID and
    RAZORPAY_KEY_SECRET to be set in the environment (rzp_test_... keys only).

    Run manually before demo:
        .venv\\Scripts\\pytest.exe -v -m integration

    Asserts:
    - HTTP 200 response from /agent/purchase.
    - decision == "APPROVED" for KB001.
    - payment.status == "created".
    - razorpay_order_id starts with "order_" (Razorpay convention).
    - No real money moves — Test Mode only.
    """
    response = client.post("/agent/purchase", json={
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["payment"] is not None
    assert data["payment"]["status"] == "created"
    assert data["payment"]["razorpay_order_id"].startswith("order_")
    assert data["payment"]["error"] is None
    # Verify amount in paise was correctly computed: ₹1,499 = 149900 paise
    # (Razorpay echoes amount back in the order response)
    assert data["amount"] == 1499.0

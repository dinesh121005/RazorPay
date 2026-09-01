import sqlite3
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.audit import audit_store
from app.main import app

client = TestClient(app)

_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_RouterTest_123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "some-receipt-id",
}


def test_agent_purchase_approved_canonical():
    """
    1. CUST001 + KB001, qty 1 -> HTTP 200, decision == 'APPROVED'.
    KB001 price is ₹1,499 <= CUST001 limit of ₹2,000.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)

    assert response.status_code == 200
    mock_create.assert_called_once()

    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "KB001"
    assert data["amount"] == 1499.0
    assert data["mandate_limit"] == 2000.0
    assert "within mandate limit" in data["reason"]
    assert "1499.00" in data["reason"]


def test_agent_purchase_rejected_over_limit_canonical():
    """
    2. CUST001 + MN001, qty 1 -> HTTP 200, decision == 'REJECTED'.
    MN001 price is ₹4,999 > CUST001 limit of ₹2,000.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "MN001",
        "quantity": 1
    }
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)
    mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["product_id"] == "MN001"
    assert data["amount"] == 4999.0
    assert data["mandate_limit"] == 2000.0
    assert "exceeds maximum mandate limit" in data["reason"]
    assert "4999.00" in data["reason"]


def test_agent_purchase_unknown_product_returns_404():
    """
    3. Unknown product_id -> HTTP 404 before touching policy engine.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "NON_EXISTENT_PROD_999",
        "quantity": 1
    }
    response = client.post("/agent/purchase", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "NON_EXISTENT_PROD_999" in data["detail"]


def test_agent_purchase_unknown_customer_returns_404():
    """
    4. Unknown customer_id -> HTTP 404 before touching policy engine.
    """
    payload = {
        "customer_id": "NON_EXISTENT_CUST_999",
        "product_id": "KB001",
        "quantity": 1
    }
    response = client.post("/agent/purchase", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "NON_EXISTENT_CUST_999" in data["detail"]


def test_agent_purchase_quantity_exceeds_mandate_limit():
    """
    5. Quantity that pushes an otherwise-approved item over limit:
    KB001 (₹1,499) x 2 = ₹2,998 > ₹2,000 -> HTTP 200, decision == 'REJECTED'.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 2
    }
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)
    mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["product_id"] == "KB001"
    assert data["amount"] == 2998.0
    assert data["mandate_limit"] == 2000.0
    assert "2998.00" in data["reason"]
    assert "exceeds maximum mandate limit" in data["reason"]


def test_agent_purchase_default_quantity():
    """
    When quantity is omitted, it defaults to 1.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001"
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)
    mock_create.assert_called_once()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "KB001"
    assert data["amount"] == 1499.0
    assert data["mandate_limit"] == 2000.0


def test_agent_purchase_invalid_quantity_validation_error():
    """
    Quantity must be >= 1; 0 or negative quantities result in HTTP 422 Unprocessable Entity.
    """
    payload_zero = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 0
    }
    response = client.post("/agent/purchase", json=payload_zero)
    assert response.status_code == 422

    payload_neg = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": -2
    }
    response = client.post("/agent/purchase", json=payload_neg)
    assert response.status_code == 422


def test_agent_purchase_stock_exceeded_returns_400():
    """
    When requested quantity exceeds product inventory stock, return HTTP 400.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",  # stock is 20
        "quantity": 25
    }
    response = client.post("/agent/purchase", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "exceeds available inventory" in data["detail"]


def test_agent_purchase_idempotency_returns_cached_response():
    """
    Retried purchase with same explicit idempotency_key returns cached response and only calls Razorpay once.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
        "idempotency_key": "idemp-key-test-999"
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response1 = client.post("/agent/purchase", json=payload)
        response2 = client.post("/agent/purchase", json=payload)

    assert response1.status_code == 200
    assert response2.status_code == 200
    mock_create.assert_called_once()

    data1 = response1.json()
    data2 = response2.json()
    assert data1["transaction_id"] == data2["transaction_id"]
    assert data1["payment"]["razorpay_order_id"] == data2["payment"]["razorpay_order_id"]
    assert data1["idempotency_key"] == "idemp-key-test-999"
    assert data2["idempotency_key"] == "idemp-key-test-999"


def test_agent_purchase_omitted_idempotency_key_collapses_within_60s():
    """
    When idempotency_key is omitted, purchases within the same 60-second window
    are automatically deduplicated via deterministic bucket hashing.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
    }
    with patch("time.time", return_value=1700000040.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response1 = client.post("/agent/purchase", json=payload)
    with patch("time.time", return_value=1700000050.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create2:
        response2 = client.post("/agent/purchase", json=payload)

    assert response1.status_code == 200
    assert response2.status_code == 200
    mock_create.assert_called_once()
    mock_create2.assert_not_called()

    data1 = response1.json()
    data2 = response2.json()
    assert data1["transaction_id"] == data2["transaction_id"]
    assert data1["payment"]["razorpay_order_id"] == data2["payment"]["razorpay_order_id"]
    assert data1["idempotency_key"] == data2["idempotency_key"]
    assert data1["idempotency_key"] is not None


def test_agent_purchase_omitted_idempotency_key_rolls_over_new_window():
    """
    When idempotency_key is omitted, purchases in different 60-second windows
    generate distinct keys and create distinct transactions.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
    }
    with patch("time.time", return_value=1700000040.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create1:
        response1 = client.post("/agent/purchase", json=payload)

    with patch("time.time", return_value=1700000120.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create2:
        response2 = client.post("/agent/purchase", json=payload)

    assert response1.status_code == 200
    assert response2.status_code == 200
    mock_create1.assert_called_once()
    mock_create2.assert_called_once()

    data1 = response1.json()
    data2 = response2.json()
    assert data1["transaction_id"] != data2["transaction_id"]
    assert data1["idempotency_key"] != data2["idempotency_key"]


def test_agent_purchase_idempotency_race_condition_forced():
    """
    Simulates a race condition where two concurrent requests with identical idempotency_key
    both pass the initial check (lookup returns None for both before either writes).
    The second write triggers a UNIQUE constraint violation in SQLite, which is caught,
    re-queried, and returns the cached result without duplicate payment or duplicate audit rows.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
        "idempotency_key": "race-test-key-001",
    }
    real_get = audit_store.get_by_idempotency_key
    lookup_calls = 0

    def mock_get_by_idempotency_key(key: str):
        nonlocal lookup_calls
        lookup_calls += 1
        # For the first 2 initial lookups (simulating 2 concurrent racers), return None
        if lookup_calls <= 2:
            return None
        # On subsequent lookups (inside the IntegrityError catch handler), delegate to real DB lookup
        return real_get(key)

    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        with patch.object(audit_store, "get_by_idempotency_key", side_effect=mock_get_by_idempotency_key):
            # Call 1 inserts row and creates order
            resp1 = client.post("/agent/purchase", json=payload)
            # Call 2 bypassed initial lookup, attempts insert -> hits UNIQUE constraint -> catches -> returns resp1
            resp2 = client.post("/agent/purchase", json=payload)

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    data1 = resp1.json()
    data2 = resp2.json()
    assert data1["decision"] == "APPROVED"
    assert data2["decision"] == "APPROVED"
    assert data1["transaction_id"] == data2["transaction_id"]
    assert data1["payment"]["razorpay_order_id"] == data2["payment"]["razorpay_order_id"]

    # Exactly ONE Razorpay order created
    mock_create.assert_called_once()

    # Exactly ONE audit row in database
    records = audit_store.list(customer_id="CUST001")
    assert len(records) == 1


def test_agent_purchase_operational_error_graceful_cached_recovery():
    """
    When write_proposal raises sqlite3.OperationalError('database is locked') due to
    concurrent lock contention, but another request already committed the row with the same
    idempotency_key, execute_purchase catches it, retrieves the cached row, and succeeds.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
        "idempotency_key": "lock-contention-test-key-001",
    }
    # 1. First request succeeds normally and seeds the database
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        resp1 = client.post("/agent/purchase", json=payload)
    assert resp1.status_code == 200
    mock_create.assert_called_once()
    txn_id = resp1.json()["transaction_id"]

    # 2. Second request simulates bypassing initial lookup and hitting 'database is locked' on write
    real_get = audit_store.get_by_idempotency_key
    lookup_calls = 0

    def mock_get(key: str):
        nonlocal lookup_calls
        lookup_calls += 1
        # First lookup returns None to force execution into write_proposal
        if lookup_calls == 1:
            return None
        return real_get(key)

    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create2:
        with patch.object(audit_store, "get_by_idempotency_key", side_effect=mock_get):
            with patch.object(audit_store, "write_proposal", side_effect=sqlite3.OperationalError("database is locked")):
                resp2 = client.post("/agent/purchase", json=payload)

    assert resp2.status_code == 200
    assert resp2.json()["decision"] == "APPROVED"
    assert resp2.json()["transaction_id"] == txn_id
    mock_create2.assert_not_called()


def test_agent_purchase_unrelated_operational_error_re_raises():
    """
    A genuinely unrelated sqlite3.OperationalError (e.g. disk I/O failure) where no
    matching record exists in the audit store must be re-raised, not swallowed.
    """
    import pytest
    from app.agent.service import execute_purchase

    with patch.object(audit_store, "write_proposal", side_effect=sqlite3.OperationalError("disk I/O error")):
        with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
            execute_purchase(
                customer_id="CUST001",
                product_id="KB001",
                quantity=1,
                idempotency_key="unrelated-disk-error-key",
            )


def test_agent_purchase_other_approved_product():
    """
    HK001 (₹499) x 3 = ₹1,497 <= ₹2,000 -> HTTP 200, decision == 'APPROVED'.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "HK001",
        "quantity": 3
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)
    mock_create.assert_called_once()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "HK001"
    assert data["amount"] == 1497.0
    assert data["mandate_limit"] == 2000.0


# ==========================================
# Multi-Merchant Catalog Foundation (Piece A)
# ==========================================

def test_agent_purchase_cross_merchant_food_approved():
    """
    6a. CUST001 buys FD001 (Coconut Oil, ₹349, category='food', merchant_id='MERCH_FOOD')
    via POST /agent/purchase.
    Proves end-to-end: cross-merchant + cross-category purchase correctly APPROVED within limit.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "FD001",
        "quantity": 1,
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)
    mock_create.assert_called_once()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0
    assert data["mandate_limit"] == 2000.0


def test_agent_purchase_merchant_not_in_mandate_rejected():
    """
    6b. CUST002 attempts to buy FD001 (merchant_id='MERCH_FOOD') via POST /agent/purchase.
    CUST002's mandate only allows MERCH_ELEC — MERCH_FOOD is deliberately excluded.
    Proves the router's per-product merchant derivation (product.merchant_id) is what reaches the
    Policy Engine and causes a real MERCHANT_NOT_ALLOWED rejection — not a tautological evaluate() call.
    If router.py ever reverts to a hardcoded merchant constant, this test will regress.
    """
    payload = {
        "customer_id": "CUST002",
        "product_id": "FD001",
        "quantity": 1,
    }
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload)
    mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0
    assert data["mandate_limit"] == 1500.0
    # Reason must cite the unauthorized merchant — engine text: "is not authorized in customer mandate"
    assert "MERCH_FOOD" in data["reason"]
    assert "not authorized" in data["reason"]

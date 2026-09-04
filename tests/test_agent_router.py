import sqlite3
import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.audit import audit_store
from app.main import app
from app.oauth.crypto import create_access_token

client = TestClient(app)

_ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-secret-key"}


_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_RouterTest_123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "some-receipt-id",
}


def _get_oauth_headers(customer_id: str = "CUST001") -> dict:
    token = create_access_token(customer_id=customer_id)
    return {"Authorization": f"Bearer {token}"}



def test_agent_purchase_unauthenticated_returns_401():
    """
    POST /agent/purchase without OAuth Bearer token or Admin API Key must return 401.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 1,
    }
    response = client.post("/agent/purchase", json=payload)
    assert response.status_code == 401


def test_agent_purchase_approved_micro_flow_under_threshold():
    """
    Micro-purchases under ₹500 (e.g. FD001, ₹349) execute autonomously without gating.
    FD001 price is ₹349 <= CUST001 limit of ₹2,000 and < ₹500 threshold.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "FD001",
        "quantity": 1,
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    mock_create.assert_called_once()

    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0
    assert data["mandate_limit"] == 2000.0
    assert "within mandate limit" in data["reason"]
    assert "349.00" in data["reason"]


def test_agent_purchase_gated_two_step_confirmation_flow():
    """
    Transactions >= ₹500 return PENDING_CONFIRMATION with confirmation_token,
    which is then executed via POST /agent/confirm.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",  # ₹1,499 >= ₹500
        "quantity": 1,
    }
    # Step 1: Propose (Gated)
    with patch(_CREATE_ORDER) as mock_create_1:
        resp1 = client.post("/agent/purchase", json=payload, headers=_get_oauth_headers("CUST001"))

    assert resp1.status_code == 200
    mock_create_1.assert_not_called()
    data1 = resp1.json()
    assert data1["decision"] == "PENDING_CONFIRMATION"
    assert data1["requires_confirmation"] is True
    assert data1["confirmation_token"] is not None
    token = data1["confirmation_token"]

    # Step 2: Confirm Purchase
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create_2:
        resp2 = client.post(
            "/agent/confirm",
            json={"confirmation_token": token},
            headers=_get_oauth_headers("CUST001"),
        )

    assert resp2.status_code == 200
    mock_create_2.assert_called_once()
    data2 = resp2.json()
    assert data2["decision"] == "APPROVED"
    assert data2["payment"]["razorpay_order_id"] == "order_RouterTest_123"


def test_agent_purchase_micro_transaction_auto_executes():
    """
    Transactions < ₹500 (e.g. FD001 at ₹349) auto-execute without gating.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "FD001",  # ₹349 < ₹500
        "quantity": 1,
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    mock_create.assert_called_once()
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["requires_confirmation"] is False


def test_agent_purchase_rejected_over_limit_canonical():
    """
    2. CUST001 + MN001, qty 1 -> HTTP 200, decision == 'REJECTED'.
    MN001 price is ₹4,999 > CUST001 limit of ₹2,000.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "MN001",
        "quantity": 1,
    }
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
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
        "quantity": 1,
    }
    response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
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
        "quantity": 1,
    }
    response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
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
        "quantity": 2,
    }
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
    mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["product_id"] == "KB001"
    assert data["amount"] == 2998.0
    assert data["mandate_limit"] == 2000.0
    assert "2998.00" in data["reason"]
    assert "exceeds maximum mandate limit" in data["reason"]


def test_agent_purchase_invalid_quantity_validation_error():
    """
    Quantity must be >= 1; 0 or negative quantities result in HTTP 422 Unprocessable Entity.
    """
    payload_zero = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": 0,
    }
    response = client.post("/agent/purchase", json=payload_zero, headers=_ADMIN_HEADERS)
    assert response.status_code == 422

    payload_neg = {
        "customer_id": "CUST001",
        "product_id": "KB001",
        "quantity": -2,
    }
    response = client.post("/agent/purchase", json=payload_neg, headers=_ADMIN_HEADERS)
    assert response.status_code == 422


def test_agent_purchase_stock_exceeded_returns_400():
    """
    When requested quantity exceeds product inventory stock, return HTTP 400.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "KB001",  # stock is 20
        "quantity": 25,
    }
    response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
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
        "product_id": "FD001",
        "quantity": 1,
        "idempotency_key": "idemp-key-test-999",
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response1 = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
        response2 = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)

    assert response1.status_code == 200
    assert response2.status_code == 200
    mock_create.assert_called_once()

    data1 = response1.json()
    data2 = response2.json()
    assert data1["transaction_id"] == data2["transaction_id"]
    assert data1["payment"]["razorpay_order_id"] == data2["payment"]["razorpay_order_id"]
    assert data1["idempotency_key"] == "idemp-key-test-999"
    assert data2["idempotency_key"] == "idemp-key-test-999"


def test_agent_purchase_cross_merchant_food_approved():
    """
    CUST001 buys FD001 (Coconut Oil, ₹349, category='food', merchant_id='MERCH_FOOD')
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "FD001",
        "quantity": 1,
    }
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
    mock_create.assert_called_once()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0
    assert data["mandate_limit"] == 2000.0


def test_agent_purchase_merchant_not_in_mandate_rejected():
    """
    CUST002 attempts to buy FD001 (merchant_id='MERCH_FOOD').
    CUST002's mandate only allows MERCH_ELEC.
    """
    payload = {
        "customer_id": "CUST002",
        "product_id": "FD001",
        "quantity": 1,
    }
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json=payload, headers=_ADMIN_HEADERS)
    mock_create.assert_not_called()

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0
    assert data["mandate_limit"] == 1500.0
    assert "MERCH_FOOD" in data["reason"]
    assert "not authorized" in data["reason"]


def test_recommend_addons_endpoint():
    """
    POST /merchant/recommend-addons returns smart upsell suggestions within headroom.
    """
    payload = {
        "product_id": "KB001",
        "remaining_budget": 1000.0,
    }
    response = client.post("/merchant/recommend-addons", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["base_product_id"] == "KB001"
    assert len(data["addons"]) > 0
    # Add-on price must be <= 1000
    for addon in data["addons"]:
        assert addon["price_per_unit"] <= 1000.0


def test_confirmation_token_replay_is_idempotent():
    """
    Verifies that calling /agent/confirm with the same valid confirmation token multiple times
    is idempotent: it returns the existing confirmed transaction and does NOT call Razorpay twice.
    """
    # 1. Propose purchase for KB001 (₹1,499 >= ₹500 gating threshold)
    propose_resp = client.post(
        "/agent/purchase",
        json={"customer_id": "CUST001", "product_id": "KB001", "quantity": 1},
        headers=_ADMIN_HEADERS,
    )
    assert propose_resp.status_code == 200
    propose_data = propose_resp.json()
    assert propose_data["requires_confirmation"] is True
    token = propose_data["confirmation_token"]
    assert token is not None

    # 2. First confirmation call: mints Razorpay order
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        confirm_resp1 = client.post(
            "/agent/confirm",
            json={"confirmation_token": token, "customer_id": "CUST001"},
            headers=_ADMIN_HEADERS,
        )
    mock_create.assert_called_once()
    assert confirm_resp1.status_code == 200
    data1 = confirm_resp1.json()
    assert data1["decision"] == "APPROVED"
    assert data1["transaction_id"] is not None

    # 3. Second confirmation call with the SAME token (replay attack / duplicate network call)
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create_replay:
        confirm_resp2 = client.post(
            "/agent/confirm",
            json={"confirmation_token": token, "customer_id": "CUST001"},
            headers=_ADMIN_HEADERS,
        )
    # Must NOT call Razorpay again
    mock_create_replay.assert_not_called()
    assert confirm_resp2.status_code == 200
    data2 = confirm_resp2.json()
    assert data2["decision"] == "APPROVED"
    assert data2["transaction_id"] == data1["transaction_id"]


def test_confirmation_policy_re_evaluation_rejects_if_mandate_revoked():
    """
    Verifies that if a mandate is updated/revoked between proposal and confirmation,
    the confirmation is rejected before payment execution.
    """
    from app.policy.store import mandate_store

    # 1. Propose purchase for KB001 (₹1,499)
    propose_resp = client.post(
        "/agent/purchase",
        json={"customer_id": "CUST001", "product_id": "KB001", "quantity": 1},
        headers=_ADMIN_HEADERS,
    )
    assert propose_resp.status_code == 200
    token = propose_resp.json()["confirmation_token"]

    # 2. Lower customer mandate limit to ₹1,000 (below ₹1,499) before confirmation
    orig_mandate = mandate_store.get_mandate("CUST001")
    orig_limit = orig_mandate.max_transaction_amount
    mandate_store.update_mandate_limit(
        customer_id="CUST001",
        new_limit=1000.0,
    )

    try:
        with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
            confirm_resp = client.post(
                "/agent/confirm",
                json={"confirmation_token": token, "customer_id": "CUST001"},
                headers=_ADMIN_HEADERS,
            )
        mock_create.assert_not_called()
        assert confirm_resp.status_code == 422
        assert "Policy evaluation rejected" in confirm_resp.json()["detail"]
    finally:
        # Restore original mandate limit
        mandate_store.update_mandate_limit(
            customer_id="CUST001",
            new_limit=orig_limit,
        )


def test_auto_pay_fails_if_sandbox_wallet_balance_insufficient():
    """
    Verifies that if customer sandbox mandate wallet balance is insufficient,
    the purchase execution halts with PAYMENT_FAILED and does NOT decrement stock or capture payment.
    """
    from app.wallet.store import wallet_store
    from app.catalog.service import get_product

    # Drain wallet balance for CUST001 to ₹0.00
    wallet_store.set_balance("CUST001", 0.0)
    stock_before = get_product("FD001").stock

    # Attempt micro-purchase (FD001 @ ₹349, under ₹500 auto-confirm threshold)
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        resp = client.post(
            "/agent/purchase",
            json={"customer_id": "CUST001", "product_id": "FD001", "quantity": 1},
            headers=_ADMIN_HEADERS,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "PAYMENT_FAILED"
    assert "sandbox mandate wallet debit failed" in data["reason"]
    assert data["payment"]["status"] == "failed"

    # Stock must NOT have decremented
    stock_after = get_product("FD001").stock
    assert stock_after == stock_before




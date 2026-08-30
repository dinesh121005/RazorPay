import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


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
    response = client.post("/agent/purchase", json=payload)
    assert response.status_code == 200

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
    response = client.post("/agent/purchase", json=payload)
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
    response = client.post("/agent/purchase", json=payload)
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
    response = client.post("/agent/purchase", json=payload)
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


def test_agent_purchase_other_approved_product():
    """
    HK001 (₹499) x 3 = ₹1,497 <= ₹2,000 -> HTTP 200, decision == 'APPROVED'.
    """
    payload = {
        "customer_id": "CUST001",
        "product_id": "HK001",
        "quantity": 3
    }
    response = client.post("/agent/purchase", json=payload)
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
    response = client.post("/agent/purchase", json=payload)
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
    response = client.post("/agent/purchase", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["decision"] == "REJECTED"
    assert data["product_id"] == "FD001"
    assert data["amount"] == 349.0
    assert data["mandate_limit"] == 1500.0
    # Reason must cite the unauthorized merchant — engine text: "is not authorized in customer mandate"
    assert "MERCH_FOOD" in data["reason"]
    assert "not authorized" in data["reason"]



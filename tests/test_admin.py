"""
Tests for Part 2 — Admin-Only Customer & Mandate Management.

Verifies:
1. Authentication: 401 Unauthorized returned when missing or invalid API key.
2. POST /admin/customers creates a usable customer mandate.
3. POST /admin/customers with duplicate customer_id returns 409 Conflict.
4. GET /admin/customers lists all stored customer mandates.
5. GET /admin/customers/{customer_id} fetches specific customer mandate or 404.
6. PATCH /admin/customers/{customer_id}/mandate modifies transaction limit or 404.
7. Dynamic customer immediately executes purchases in /agent/purchase without server restart.
8. Mandate limit increase immediately unlocks higher-priced purchases for that customer.
9. Regression test: CUST001 baseline behavior (KB001 approved, MN001 rejected) remains intact.
"""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_AdminTest_123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "some-admin-txn-id",
}


def test_admin_endpoints_require_authentication():
    """
    All admin endpoints must return HTTP 401 when accessed without authentication.
    """
    # GET /admin/customers
    res_get = client.get("/admin/customers")
    assert res_get.status_code == 401

    # POST /admin/customers
    res_post = client.post("/admin/customers", json={
        "customer_id": "CUST_UNAUTH",
        "mandate_limit": 1000.0,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["MERCH_ELEC"],
    })
    assert res_post.status_code == 401

    # PATCH /admin/customers/CUST001/mandate
    res_patch = client.patch(
        "/admin/customers/CUST001/mandate",
        headers={"X-Admin-API-Key": "wrong-key"},
        json={"mandate_limit": 5000.0}
    )
    assert res_patch.status_code == 401


def test_admin_create_customer_success(admin_headers):
    """
    POST /admin/customers creates a new customer mandate with status 201 when authenticated.
    """
    payload = {
        "customer_id": "CUST003",
        "mandate_limit": 5000.0,
        "allowed_categories": ["electronics", "food"],
        "allowed_merchants": ["MERCH_ELEC", "MERCH_FOOD"],
    }
    response = client.post("/admin/customers", json=payload, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["customer_id"] == "CUST003"
    assert data["max_transaction_amount"] == 5000.0
    assert data["allowed_categories"] == ["electronics", "food"]
    assert data["allowed_merchants"] == ["MERCH_ELEC", "MERCH_FOOD"]
    assert data["prompt_playback"] is not None


def test_admin_create_duplicate_customer_conflict(admin_headers):
    """
    POST /admin/customers returns 409 Conflict if customer_id already exists.
    """
    payload = {
        "customer_id": "CUST001",
        "mandate_limit": 2500.0,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["MERCH_ELEC"],
    }
    response = client.post("/admin/customers", json=payload, headers=admin_headers)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_admin_list_customers(admin_headers):
    """
    GET /admin/customers returns all provisioned mandates.
    """
    response = client.get("/admin/customers", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    customer_ids = [c["customer_id"] for c in data]
    assert "CUST001" in customer_ids
    assert "CUST002" in customer_ids


def test_admin_get_customer_by_id(admin_headers):
    """
    GET /admin/customers/{customer_id} returns existing customer or 404.
    """
    response_ok = client.get("/admin/customers/CUST001", headers=admin_headers)
    assert response_ok.status_code == 200
    assert response_ok.json()["customer_id"] == "CUST001"

    response_404 = client.get("/admin/customers/NON_EXISTENT", headers=admin_headers)
    assert response_404.status_code == 404


def test_admin_update_mandate_limit(admin_headers):
    """
    PATCH /admin/customers/{customer_id}/mandate updates the limit.
    """
    patch_response = client.patch(
        "/admin/customers/CUST001/mandate",
        headers=admin_headers,
        json={"mandate_limit": 10000.0}
    )
    assert patch_response.status_code == 200
    data = patch_response.json()
    assert data["customer_id"] == "CUST001"
    assert data["max_transaction_amount"] == 10000.0

    # Verify limit is updated in store
    get_response = client.get("/admin/customers/CUST001", headers=admin_headers)
    assert get_response.json()["max_transaction_amount"] == 10000.0


def test_admin_update_mandate_limit_not_found(admin_headers):
    """
    PATCH /admin/customers/{customer_id}/mandate returns 404 for unknown customer.
    """
    patch_response = client.patch(
        "/admin/customers/NON_EXISTENT/mandate",
        headers=admin_headers,
        json={"mandate_limit": 10000.0}
    )
    assert patch_response.status_code == 404


def test_dynamic_customer_immediate_purchase_execution(admin_headers):
    """
    A customer created via admin endpoint can immediately execute purchases via /agent/purchase.
    """
    # 1. Create CUST_NEW with ₹6,000 limit for electronics
    create_payload = {
        "customer_id": "CUST_NEW",
        "mandate_limit": 6000.0,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["MERCH_ELEC"],
    }
    create_res = client.post("/admin/customers", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201

    # 2. Propose purchase of MN001 (₹4,999 <= ₹6,000) -> APPROVED
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        purchase_res = client.post(
            "/agent/purchase",
            json={"customer_id": "CUST_NEW", "product_id": "MN001", "quantity": 1}
        )

    assert purchase_res.status_code == 200
    data = purchase_res.json()
    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "MN001"
    assert data["amount"] == 4999.0
    assert data["mandate_limit"] == 6000.0
    assert data["payment"]["status"] == "created"


def test_mandate_limit_patch_immediately_unlocks_purchase(admin_headers):
    """
    Updating a customer's mandate limit via PATCH immediately allows previously over-limit purchases.
    """
    # 1. Initial CUST001 limit is ₹2,000. MN001 (₹4,999) is REJECTED
    with patch(_CREATE_ORDER) as mock_create:
        res1 = client.post(
            "/agent/purchase",
            json={"customer_id": "CUST001", "product_id": "MN001", "quantity": 1}
        )
    mock_create.assert_not_called()
    assert res1.json()["decision"] == "REJECTED"

    # 2. Admin increases CUST001 limit to ₹10,000
    patch_res = client.patch(
        "/admin/customers/CUST001/mandate",
        headers=admin_headers,
        json={"mandate_limit": 10000.0}
    )
    assert patch_res.status_code == 200

    # 3. MN001 is now APPROVED
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        res2 = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "MN001",
                "quantity": 1,
                "idempotency_key": "post-limit-raise-attempt"
            }
        )
    assert res2.json()["decision"] == "APPROVED"
    assert res2.json()["mandate_limit"] == 10000.0


def test_cust001_baseline_regression():
    """
    Verify standard CUST001 baseline behavior is unchanged:
    KB001 (₹1,499) -> APPROVED, MN001 (₹4,999) -> REJECTED.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        res_kb = client.post(
            "/agent/purchase",
            json={"customer_id": "CUST001", "product_id": "KB001", "quantity": 1}
        )
    assert res_kb.status_code == 200
    assert res_kb.json()["decision"] == "APPROVED"

    with patch(_CREATE_ORDER) as mock_create:
        res_mn = client.post(
            "/agent/purchase",
            json={"customer_id": "CUST001", "product_id": "MN001", "quantity": 1}
        )
    mock_create.assert_not_called()
    assert res_mn.status_code == 200
    assert res_mn.json()["decision"] == "REJECTED"


def test_admin_create_customer_provisions_working_oauth_credentials(admin_headers):
    """
    POST /admin/customers creates mandate AND working OAuth credentials in SQLite.
    The customer can immediately complete the /oauth/authorize -> /oauth/token flow.
    """
    from app.oauth.crypto import verify_access_token
    from app.oauth.store import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, customer_auth_store

    create_payload = {
        "customer_id": "CUST_PRIYA",
        "display_name": "Priya Sharma",
        "mandate_limit": 6000.0,
        "allowed_categories": ["electronics", "food"],
        "allowed_merchants": ["MERCH_ELEC", "MERCH_FOOD"],
        "email": "priya@example.com",
        "username": "priya",
        "password": "PriyaSecurePassword123!",
    }
    create_res = client.post("/admin/customers", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201

    # 1. Credentials are authenticated in the persisted store
    cust_id = customer_auth_store.authenticate("priya", "PriyaSecurePassword123!")
    assert cust_id == "CUST_PRIYA"

    # 2. Complete /oauth/authorize
    auth_payload = {
        "username": "priya",
        "password": "PriyaSecurePassword123!",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    }
    auth_res = client.post("/oauth/authorize", json=auth_payload, headers={"Accept": "application/json"})
    assert auth_res.status_code == 200
    code = auth_res.json()["code"]

    # 3. Exchange code for access token
    token_res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    })
    assert token_res.status_code == 200
    token = token_res.json()["access_token"]

    # 4. Verify sub claim binds strictly to CUST_PRIYA
    payload = verify_access_token(token)
    assert payload["sub"] == "CUST_PRIYA"


def test_admin_create_customer_duplicate_username_rejected(admin_headers):
    """
    POST /admin/customers rejects a duplicate username with 409 Conflict.
    """
    create_payload = {
        "customer_id": "CUST_NEW",
        "display_name": "Another User",
        "mandate_limit": 3000.0,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["MERCH_ELEC"],
        "username": "dinesh",  # duplicate of CUST001's username
        "password": "somepassword123",
    }
    response = client.post("/admin/customers", json=create_payload, headers=admin_headers)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"] or "already taken" in response.json()["detail"]


def test_customer_credentials_persistence_across_store_reload(admin_headers):
    """
    Credentials created via admin survive store reload (simulating server restart).
    """
    from app.oauth.store import CustomerAuthStore, customer_auth_store

    create_payload = {
        "customer_id": "CUST_RESTART",
        "display_name": "Restart Tester",
        "mandate_limit": 4000.0,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["MERCH_ELEC"],
        "username": "restart_user",
        "password": "restart_pass_123",
    }
    res = client.post("/admin/customers", json=create_payload, headers=admin_headers)
    assert res.status_code == 201

    # Simulate fresh app startup pointing to same DB
    fresh_store = CustomerAuthStore(db_path=customer_auth_store.db_path)
    authenticated_id = fresh_store.authenticate("restart_user", "restart_pass_123")
    assert authenticated_id == "CUST_RESTART"


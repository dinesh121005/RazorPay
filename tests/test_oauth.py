"""
Unit and integration tests for minimal OAuth 2.1 authorization server (app/oauth/).
"""
import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
import jwt

from app.main import app
from app.oauth.crypto import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_SECRET,
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)
from app.oauth.store import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, auth_code_store

client = TestClient(app)


def test_crypto_password_hashing_and_verification():
    """Verifies salted PBKDF2 password hashing and constant-time verification."""
    password = "SuperSecretPassword123!"
    pw_hash, salt = hash_password(password)
    assert pw_hash is not None and len(pw_hash) == 64
    assert salt is not None and len(salt) == 32

    # Verification success
    assert verify_password(password, pw_hash, salt) is True
    # Verification failure on wrong password
    assert verify_password("WrongPassword", pw_hash, salt) is False


def test_crypto_jwt_minting_and_validation():
    """Verifies JWT token minting and signature validation."""
    token = create_access_token(customer_id="CUST001")
    payload = verify_access_token(token)

    assert payload["sub"] == "CUST001"
    assert payload["iss"] == JWT_ISSUER
    assert payload["aud"] == JWT_AUDIENCE
    assert payload["scope"] == "purchase"
    assert payload["exp"] > payload["iat"]


def test_crypto_jwt_expired_token():
    """Verifies expired JWT tokens raise PyJWTError."""
    import datetime
    expired_token = create_access_token(
        customer_id="CUST001",
        expires_delta=datetime.timedelta(seconds=-10),
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_access_token(expired_token)


def test_oauth_authorize_get_login_form():
    """GET /oauth/authorize renders HTML login form when parameters are valid."""
    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
        "state": "random-state-123",
    }
    response = client.get("/oauth/authorize", params=params)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Authorize AI Shopping Agent" in response.text
    assert "dinesh" in response.text


def test_oauth_authorize_get_invalid_client_or_uri():
    """GET /oauth/authorize rejects unknown client_id or unauthorized redirect_uri."""
    # Invalid client
    res1 = client.get("/oauth/authorize", params={
        "response_type": "code",
        "client_id": "invalid-client",
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    })
    assert res1.status_code == 400
    assert "Invalid client_id" in res1.json()["detail"]

    # Unauthorized redirect_uri
    res2 = client.get("/oauth/authorize", params={
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://malicious-attacker.com/callback",
    })
    assert res2.status_code == 400
    assert "Unauthorized redirect_uri" in res2.json()["detail"]


def test_oauth_authorize_post_success_redirect():
    """POST /oauth/authorize authenticates user and redirects with authorization code."""
    payload = {
        "username": "dinesh",
        "password": "password123",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
        "response_type": "code",
        "state": "xyz-state-999",
    }
    response = client.post("/oauth/authorize", data=payload, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://claude.ai/api/mcp/oauth_callback?")
    assert "code=" in location
    assert "state=xyz-state-999" in location


def test_oauth_authorize_post_invalid_credentials():
    """POST /oauth/authorize rejects invalid password with 401."""
    payload = {
        "username": "dinesh",
        "password": "wrong-password",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    }
    response = client.post("/oauth/authorize", data=payload)
    assert response.status_code == 401
    assert "Invalid username/email or password" in response.json()["detail"]


def test_oauth_token_exchange_success_and_sub_claim():
    """POST /oauth/token exchanges authorization code for signed JWT with sub=customer_id."""
    # 1. Obtain authorization code
    auth_payload = {
        "username": "dinesh",
        "password": "password123",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
        "state": "abc-state",
    }
    auth_res = client.post("/oauth/authorize", json=auth_payload, headers={"Accept": "application/json"})
    assert auth_res.status_code == 200
    code = auth_res.json()["code"]
    assert code is not None

    # 2. Exchange code for access token
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    }
    token_res = client.post("/oauth/token", data=token_payload)
    assert token_res.status_code == 200
    token_data = token_res.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in"] == 3600

    # 3. Verify JWT sub claim binds strictly to CUST001
    access_token = token_data["access_token"]
    payload = verify_access_token(access_token)
    assert payload["sub"] == "CUST001"


def test_oauth_token_code_reuse_rejected():
    """Authorization codes are single-use; subsequent exchange attempts must fail."""
    # 1. Issue code
    code = auth_code_store.issue_code(
        customer_id="CUST001",
        client_id=OAUTH_CLIENT_ID,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    }

    # First exchange succeeds
    res1 = client.post("/oauth/token", data=payload)
    assert res1.status_code == 200

    # Second exchange with burned code fails
    res2 = client.post("/oauth/token", data=payload)
    assert res2.status_code == 400
    assert "Invalid, expired, or previously used" in res2.json()["detail"]


def test_oauth_token_invalid_client_secret():
    """POST /oauth/token rejects invalid client_secret with 401."""
    code = auth_code_store.issue_code(
        customer_id="CUST001",
        client_id=OAUTH_CLIENT_ID,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": "wrong-secret",
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    }
    res = client.post("/oauth/token", data=payload)
    assert res.status_code == 401
    assert "Invalid client credentials" in res.json()["detail"]


def test_dynamic_customer_end_to_end_oauth_purchase(admin_headers):
    """
    End-to-end integration:
    1. Admin provisions dynamic customer CUST_DYNAMIC with custom limit ₹1,200 and credentials.
    2. Customer logs in via /oauth/authorize -> receives code -> exchanges for JWT.
    3. JWT sub binds to CUST_DYNAMIC.
    4. Tool call evaluates under CUST_DYNAMIC's ₹1,200 mandate (rejects KB001 @ ₹1,499).
    5. Admin patches limit to ₹2,500 -> Tool call is APPROVED.
    """
    from app.mcp.tools import authenticated_customer_id, propose_purchase_remote_handler

    _CREATE_ORDER = "app.payment.razorpay_client.create_order"
    _FAKE_ORDER = {
        "id": "order_DynamicOAuth_999",
        "entity": "order",
        "amount": 149900,
        "currency": "INR",
        "status": "created",
        "receipt": "dynamic-oauth-receipt",
    }

    # Step 1: Admin provisions CUST_DYNAMIC
    create_payload = {
        "customer_id": "CUST_DYNAMIC",
        "display_name": "Dynamic Buyer",
        "mandate_limit": 1200.0,
        "allowed_categories": ["electronics"],
        "allowed_merchants": ["MERCH_ELEC"],
        "username": "dynamic_buyer",
        "password": "DynPassword123!",
    }
    create_res = client.post("/admin/customers", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201

    # Step 2: Customer logs in via OAuth
    auth_res = client.post("/oauth/authorize", json={
        "username": "dynamic_buyer",
        "password": "DynPassword123!",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    }, headers={"Accept": "application/json"})
    assert auth_res.status_code == 200
    code = auth_res.json()["code"]

    # Step 3: Token exchange
    token_res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    })
    assert token_res.status_code == 200
    token = token_res.json()["access_token"]
    payload = verify_access_token(token)
    assert payload["sub"] == "CUST_DYNAMIC"

    # Step 4: Propose purchase for KB001 (₹1,499) -> rejected under ₹1,200 limit
    token_reset = authenticated_customer_id.set("CUST_DYNAMIC")
    try:
        with patch("time.time", return_value=1700000000.0), patch(_CREATE_ORDER) as mock_create_none:
            res_rejected = propose_purchase_remote_handler(
                product_id="KB001",
                quantity=1,
            )
        mock_create_none.assert_not_called()
        assert res_rejected["decision"] == "REJECTED"
        assert "exceeds maximum mandate limit" in res_rejected["reason"]

        # Step 5: Admin raises limit to ₹2,500
        patch_res = client.patch(
            "/admin/customers/CUST_DYNAMIC/mandate",
            headers=admin_headers,
            json={"mandate_limit": 2500.0},
        )
        assert patch_res.status_code == 200

        # Step 6: Propose purchase again in new time window -> PENDING_CONFIRMATION (>= ₹500)
        from app.mcp.tools import confirm_purchase_remote_handler
        with patch("time.time", return_value=1700000100.0), patch(_CREATE_ORDER) as mock_create_none:
            res_proposed = propose_purchase_remote_handler(
                product_id="KB001",
                quantity=1,
            )
        mock_create_none.assert_not_called()
        assert res_proposed["decision"] == "PENDING_CONFIRMATION"
        assert res_proposed["requires_confirmation"] is True
        token = res_proposed["confirmation_token"]

        # Step 7: Confirm Purchase -> APPROVED
        with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
            res_approved = confirm_purchase_remote_handler(
                confirmation_token=token,
            )
        mock_create.assert_called_once()
        assert res_approved["decision"] == "APPROVED"
        assert res_approved["amount"] == 1499.0
        assert res_approved["reference_code"].startswith("REF-")
    finally:
        authenticated_customer_id.reset(token_reset)



def test_oauth_authorization_server_discovery_metadata():
    """
    GET /.well-known/oauth-authorization-server returns valid RFC 8414 metadata
    with real mounted endpoint URLs matching /oauth/authorize and /oauth/token.
    """
    response = client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 200
    data = response.json()

    assert "issuer" in data
    assert data["authorization_endpoint"].endswith("/oauth/authorize")
    assert data["token_endpoint"].endswith("/oauth/token")
    assert "code" in data["response_types_supported"]
    assert "authorization_code" in data["grant_types_supported"]
    assert "refresh_token" in data["grant_types_supported"]
    assert "client_secret_post" in data["token_endpoint_auth_methods_supported"]
    assert "client_secret_basic" in data["token_endpoint_auth_methods_supported"]
    assert "purchase" in data["scopes_supported"]


def test_oauth_protected_resource_discovery_metadata():
    """
    GET /.well-known/oauth-protected-resource returns valid RFC 9470 metadata.
    """
    response = client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    data = response.json()

    assert data["resource"].endswith("/mcp")
    assert len(data["authorization_servers"]) >= 1
    assert "header" in data["bearer_methods_supported"]


def test_oauth_token_exchange_issues_refresh_token():
    """
    POST /oauth/token (authorization_code) returns access_token AND refresh_token.
    """
    # 1. Issue code
    code = auth_code_store.issue_code(
        customer_id="CUST001",
        client_id=OAUTH_CLIENT_ID,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    # 2. Exchange code
    res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None
    assert len(data["refresh_token"]) >= 32


def test_oauth_refresh_token_grant_success_and_rotation():
    """
    POST /oauth/token (grant_type=refresh_token) exchanges a valid refresh token
    for a new access token + rotated refresh token without re-authenticating.
    Old refresh token is invalidated immediately upon use.
    """
    # 1. Issue initial code & exchange for tokens
    code = auth_code_store.issue_code(
        customer_id="CUST001",
        client_id=OAUTH_CLIENT_ID,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    init_res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
    })
    assert init_res.status_code == 200
    orig_refresh = init_res.json()["refresh_token"]

    # 2. Refresh token grant
    refresh_res = client.post("/oauth/token", data={
        "grant_type": "refresh_token",
        "refresh_token": orig_refresh,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
    })
    assert refresh_res.status_code == 200
    refresh_data = refresh_res.json()
    new_access = refresh_data["access_token"]
    new_refresh = refresh_data["refresh_token"]

    # Assert new access token preserves identity
    payload = verify_access_token(new_access)
    assert payload["sub"] == "CUST001"

    # Assert token rotation occurred
    assert new_refresh != orig_refresh

    # 3. Attempt reuse of burned old refresh token must be rejected (generic 400)
    reuse_res = client.post("/oauth/token", data={
        "grant_type": "refresh_token",
        "refresh_token": orig_refresh,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
    })
    assert reuse_res.status_code == 400
    assert "Invalid, expired, or revoked refresh token" in reuse_res.json()["detail"]


def test_oauth_refresh_token_invalid_or_expired_rejected_generically():
    """
    Invalid, fake, or expired refresh tokens are rejected with a uniform generic error.
    """
    # 1. Completely bogus refresh token
    res1 = client.post("/oauth/token", data={
        "grant_type": "refresh_token",
        "refresh_token": "completely-invalid-nonexistent-token",
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
    })
    assert res1.status_code == 400
    assert "Invalid, expired, or revoked refresh token" in res1.json()["detail"]

    # 2. Expired refresh token
    from app.oauth.store import customer_auth_store
    expired_raw = customer_auth_store.issue_refresh_token(
        customer_id="CUST001",
        client_id=OAUTH_CLIENT_ID,
        ttl_days=-1,  # expired in past
    )
    res2 = client.post("/oauth/token", data={
        "grant_type": "refresh_token",
        "refresh_token": expired_raw,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
    })
    assert res2.status_code == 400
    assert "Invalid, expired, or revoked refresh token" in res2.json()["detail"]


def test_oauth_metadata_discovery_advertises_pkce_s256():
    """
    Discovery metadata endpoints must advertise PKCE S256 and public client ('none') auth.
    Required by ChatGPT connector discovery.
    """
    # RFC 8414 Authorization Server Metadata
    res1 = client.get("/.well-known/oauth-authorization-server")
    assert res1.status_code == 200
    data1 = res1.json()
    assert "S256" in data1.get("code_challenge_methods_supported", [])
    assert "none" in data1.get("token_endpoint_auth_methods_supported", [])
    assert "authorization_code" in data1.get("grant_types_supported", [])

    # OpenID Configuration alias
    res2 = client.get("/.well-known/openid-configuration")
    assert res2.status_code == 200
    data2 = res2.json()
    assert "S256" in data2.get("code_challenge_methods_supported", [])
    assert "none" in data2.get("token_endpoint_auth_methods_supported", [])


def test_oauth_pkce_s256_full_flow_success():
    """
    Full end-to-end OAuth 2.1 PKCE (RFC 7636) flow:
    1. Client generates code_verifier and computes S256 code_challenge.
    2. Authorizes via /oauth/authorize with challenge and client_id='chatgpt'.
    3. Exchanges code + verifier at /oauth/token without client_secret (public client).
    4. Validates JWT access token issued.
    """
    import base64
    import hashlib
    import secrets

    # 1. Generate RFC 7636 PKCE code_verifier and code_challenge (S256)
    code_verifier = secrets.token_urlsafe(40)  # > 43 chars
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")

    # 2. Authorize
    auth_res = client.post("/oauth/authorize", json={
        "username": "dinesh",
        "password": "password123",
        "client_id": "chatgpt",
        "redirect_uri": "https://chatgpt.com/api/aip/v1/auth/oauth/callback",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": "chatgpt-session-42",
    }, headers={"Accept": "application/json"})
    assert auth_res.status_code == 200
    code = auth_res.json()["code"]
    assert code is not None

    # 3. Exchange code for access token using code_verifier (no client_secret needed for PKCE public client)
    token_res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": "chatgpt",
        "redirect_uri": "https://chatgpt.com/api/aip/v1/auth/oauth/callback",
        "code_verifier": code_verifier,
    })
    assert token_res.status_code == 200
    token_data = token_res.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in"] == 3600
    assert "access_token" in token_data
    assert "refresh_token" in token_data

    # 4. Verify identity bound to token
    payload = verify_access_token(token_data["access_token"])
    assert payload["sub"] == "CUST001"


def test_oauth_pkce_s256_invalid_verifier_rejected():
    """
    RFC 7636: Providing an incorrect code_verifier must fail the token exchange.
    """
    import base64
    import hashlib
    import secrets

    code_verifier = secrets.token_urlsafe(40)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")

    auth_res = client.post("/oauth/authorize", json={
        "username": "dinesh",
        "password": "password123",
        "client_id": "chatgpt",
        "redirect_uri": "https://chatgpt.com/api/aip/v1/auth/oauth/callback",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }, headers={"Accept": "application/json"})
    assert auth_res.status_code == 200
    code = auth_res.json()["code"]

    # Exchange with incorrect code_verifier
    token_res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": "chatgpt",
        "redirect_uri": "https://chatgpt.com/api/aip/v1/auth/oauth/callback",
        "code_verifier": "wrong-verifier-123456789012345678901234567890",
    })
    assert token_res.status_code == 400
    assert "invalid" in token_res.json()["detail"].lower()


def test_oauth_pkce_missing_verifier_when_challenge_present_rejected():
    """
    When an auth code was issued with PKCE code_challenge, attempting to exchange
    without code_verifier (and without valid confidential client credentials) must be rejected.
    """
    import base64
    import hashlib
    import secrets

    code_verifier = secrets.token_urlsafe(40)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")

    auth_res = client.post("/oauth/authorize", json={
        "username": "dinesh",
        "password": "password123",
        "client_id": "chatgpt",
        "redirect_uri": "https://chatgpt.com/api/aip/v1/auth/oauth/callback",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }, headers={"Accept": "application/json"})
    assert auth_res.status_code == 200
    code = auth_res.json()["code"]

    # Exchange without code_verifier and without secret
    token_res = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": "chatgpt",
        "redirect_uri": "https://chatgpt.com/api/aip/v1/auth/oauth/callback",
    })
    assert token_res.status_code == 401
    assert "Invalid client credentials" in token_res.json()["detail"]




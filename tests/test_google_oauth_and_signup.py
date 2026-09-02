"""
Tests for Self-Service Registration and Google OAuth SSO.
"""
import base64
import json
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.oauth.store import customer_auth_store, auth_code_store
from app.policy.store import mandate_store

client = TestClient(app)


def test_authorize_page_renders_google_and_signup():
    """Verify that /oauth/authorize contains Google SSO button and Sign Up tab."""
    response = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "claude-desktop-client",
            "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
            "state": "test_state_123",
        }
    )
    assert response.status_code == 200
    html = response.text
    assert "Continue with Google" in html
    assert "/oauth/google/login" in html
    assert "Create Account" in html
    assert "/oauth/register" in html
    assert "Sign In" in html


def test_self_service_registration_success():
    """Verify new user can register via /oauth/register and receives auth code redirect."""
    response = client.post(
        "/oauth/register",
        data={
            "display_name": "Test Self User",
            "username": "test_self_user_99",
            "email": "test_self_user_99@example.com",
            "password": "SecurePassword123!",
            "client_id": "claude-desktop-client",
            "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
            "state": "state_reg_xyz",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://claude.ai/api/mcp/oauth_callback")
    assert "code=" in location
    assert "state=state_reg_xyz" in location

    # Verify user exists in customer_auth_store
    user = customer_auth_store.get_user_by_username("test_self_user_99")
    assert user is not None
    assert user.email == "test_self_user_99@example.com"

    # Verify mandate exists in mandate_store
    mandate = mandate_store.get_mandate(user.customer_id)
    assert mandate is not None
    assert mandate.max_transaction_amount == 2000.0
    assert mandate.display_name == "Test Self User"


def test_self_service_registration_duplicate_rejection():
    """Verify duplicate registration attempts are rejected with 409 Conflict."""
    # Attempt duplicate registration with dinesh (seeded user)
    response = client.post(
        "/oauth/register",
        data={
            "display_name": "Duplicate Dinesh",
            "username": "dinesh",
            "email": "dinesh_diff@example.com",
            "password": "password123",
            "client_id": "claude-desktop-client",
            "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
        },
    )
    assert response.status_code == 409
    assert "already taken" in response.json()["detail"]


def test_google_login_redirect():
    """Verify /oauth/google/login generates correct Google authorization URL."""
    response = client.get(
        "/oauth/google/login",
        params={
            "client_id": "claude-desktop-client",
            "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
            "state": "custom_claude_state_456",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    google_url = response.headers["location"]
    assert google_url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "client_id=" in google_url
    assert "redirect_uri=" in google_url
    assert "state=" in google_url


@pytest.mark.anyio
async def test_google_callback_auto_provisioning():
    """Verify Google OAuth callback auto-provisions a new customer and returns auth code."""
    # Prepare mock state
    state_payload = {
        "client_id": "claude-desktop-client",
        "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
        "state": "google_test_state_789",
        "scope": "purchase",
    }
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

    from unittest.mock import MagicMock
    mock_token_res = MagicMock()
    mock_token_res.status_code = 200
    mock_token_res.json.return_value = {"access_token": "fake_google_access_token_123"}

    mock_userinfo_res = MagicMock()
    mock_userinfo_res.status_code = 200
    mock_userinfo_res.json.return_value = {
        "email": "google_new_shopper@gmail.com",
        "name": "Google New Shopper",
        "sub": "google_sub_12345678",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_res), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_userinfo_res):
        
        response = client.get(
            "/oauth/google/callback",
            params={
                "code": "mock_google_auth_code",
                "state": encoded_state,
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    target = response.headers["location"]
    assert target.startswith("https://claude.ai/api/mcp/oauth_callback")
    assert "code=" in target
    assert "state=google_test_state_789" in target

    # Verify customer was auto-provisioned
    user = customer_auth_store.get_user_by_email("google_new_shopper@gmail.com")
    assert user is not None
    mandate = mandate_store.get_mandate(user.customer_id)
    assert mandate is not None
    assert mandate.max_transaction_amount == 2000.0
    assert mandate.display_name == "Google New Shopper"

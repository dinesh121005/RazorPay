"""
Authentication and authorization module for administrative and audit endpoints.

Enforces API key / Bearer token security on administrative operations to prevent
unauthorized mandate tampering or data leakage.
"""
import os
from typing import Optional
from fastapi import Header, HTTPException, status


from typing import Optional
from fastapi import HTTPException, Request, status


def get_admin_api_key() -> str:
    """
    Retrieve the configured ADMIN_API_KEY from the environment.
    Defaults to 'dev-admin-secret-key' in development/test if not set.
    """
    return os.environ.get("ADMIN_API_KEY", "dev-admin-secret-key")


def verify_admin_key(request: Request) -> str:
    """
    FastAPI dependency validating that the caller holds valid admin credentials.
    Accepts either:
      - 'X-Admin-API-Key: <key>'
      - 'Authorization: Bearer <key>'
    """
    expected_key = get_admin_api_key()

    provided_key = request.headers.get("x-admin-api-key")
    if not provided_key:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[len("Bearer "):].strip()

    if not provided_key or provided_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing or invalid Admin API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return provided_key


def verify_agent_or_admin_auth(request: Request) -> dict:
    """
    FastAPI dependency validating that the caller is authenticated as an AI Agent
    (via OAuth 2.1 Bearer JWT token) OR as a System Administrator (via Admin API Key).

    Returns a dict with:
      {"auth_type": "admin", "customer_id": None} OR
      {"auth_type": "oauth", "customer_id": "<sub_claim>"}
    """
    expected_admin_key = get_admin_api_key()

    # 1. Check X-Admin-API-Key
    x_admin_key = request.headers.get("x-admin-api-key")
    if x_admin_key and x_admin_key.strip() == expected_admin_key:
        return {"auth_type": "admin", "customer_id": None}

    # 2. Check Authorization Header
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        if token == expected_admin_key:
            return {"auth_type": "admin", "customer_id": None}

        # Attempt to decode as OAuth JWT Access Token
        try:
            from app.oauth.crypto import verify_access_token
            payload = verify_access_token(token)
            customer_id = payload.get("sub")
            if not customer_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized: Access token missing 'sub' claim",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return {"auth_type": "oauth", "customer_id": customer_id}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unauthorized: Invalid or expired OAuth access token ({str(exc)})",
                headers={"WWW-Authenticate": "Bearer"},
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid OAuth Bearer token or Admin API Key required",
        headers={"WWW-Authenticate": "Bearer"},
    )



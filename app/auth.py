"""
Authentication and authorization module for administrative and audit endpoints.

Enforces API key / Bearer token security on administrative operations to prevent
unauthorized mandate tampering or data leakage.
"""
import os
from typing import Optional
from fastapi import Header, HTTPException, status


def get_admin_api_key() -> str:
    """
    Retrieve the configured ADMIN_API_KEY from the environment.
    Defaults to 'dev-admin-secret-key' in development/test if not set.
    """
    return os.environ.get("ADMIN_API_KEY", "dev-admin-secret-key")


def verify_admin_key(
    x_admin_api_key: Optional[str] = Header(default=None, alias="X-Admin-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    FastAPI dependency validating that the caller holds valid admin credentials.
    Accepts either:
      - 'X-Admin-API-Key: <key>'
      - 'Authorization: Bearer <key>'
    """
    expected_key = get_admin_api_key()

    provided_key = None
    if x_admin_api_key:
        provided_key = x_admin_api_key
    elif authorization and authorization.startswith("Bearer "):
        provided_key = authorization[len("Bearer "):].strip()

    if not provided_key or provided_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing or invalid Admin API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return provided_key

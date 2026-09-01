"""
Cryptographic helpers for password hashing and signed JWT token management.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import jwt

# Secret for signing JWT access tokens
JWT_SECRET = os.getenv("JWT_SECRET", "dev-oauth-jwt-secret-key-change-in-prod-32chars")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "ai-buyer-gateway"
JWT_AUDIENCE = "ai-buyer-gateway-mcp"
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations.
    Returns (password_hash_hex, salt_hex).
    """
    if salt is None:
        salt = secrets.token_hex(16)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        100000,
    )
    return hash_bytes.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """
    Verifies a plaintext password against a stored PBKDF2 hash and salt.
    Uses constant-time comparison to prevent timing attacks.
    """
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)


def create_access_token(
    customer_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Mints a signed JWT access token with the customer_id bound strictly to the `sub` claim.
    """
    now = datetime.now(timezone.utc)
    expiry = now + (expires_delta or timedelta(seconds=TOKEN_EXPIRY_SECONDS))

    payload: Dict[str, Any] = {
        "sub": customer_id,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
        "scope": "purchase",
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verifies and decodes a signed JWT access token.
    Raises jwt.PyJWTError (ExpiredSignatureError, InvalidTokenError) on verification failure.
    """
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )

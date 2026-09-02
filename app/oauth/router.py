"""
OAuth 2.1 minimal authorization server endpoints, discovery metadata, and token grants.
"""
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.oauth.crypto import create_access_token
from app.oauth.models import TokenRequest, TokenResponse
from app.oauth.store import (
    ALLOWED_REDIRECT_URIS,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    auth_code_store,
    customer_auth_store,
    is_allowed_redirect_uri,
)

router = APIRouter(tags=["oauth"])


def _validate_client_credentials(
    client_id: Optional[str],
    client_secret: Optional[str],
    auth_header: Optional[str] = None,
) -> bool:
    """Validates client_id and client_secret from body or Authorization: Basic header."""
    # Check Basic Auth header
    if auth_header and auth_header.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            h_client_id, h_client_secret = decoded.split(":", 1)
            return h_client_id == OAUTH_CLIENT_ID and h_client_secret == OAUTH_CLIENT_SECRET
        except Exception:
            return False

    return client_id == OAUTH_CLIENT_ID and client_secret == OAUTH_CLIENT_SECRET


# -----------------------------------------------------------------------------
# Discovery Metadata Endpoints (RFC 8414 & RFC 9470 / RFC 9728)
# -----------------------------------------------------------------------------
@router.get(
    "/.well-known/oauth-authorization-server",
    summary="OAuth 2.0 Authorization Server Metadata (RFC 8414)",
    description="Public discovery endpoint describing supported endpoints, grant types, and auth methods."
)
def get_oauth_authorization_server_metadata(request: Request) -> dict:
    """Public endpoint returning OAuth 2.0 Authorization Server Metadata."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "scopes_supported": ["purchase"],
        "code_challenge_methods_supported": [],
    }


@router.get(
    "/.well-known/oauth-protected-resource",
    summary="OAuth 2.0 Protected Resource Metadata (RFC 9470 / RFC 9728)",
    description="Public discovery endpoint describing protected resource URL and authorization servers."
)
def get_oauth_protected_resource_metadata(request: Request) -> dict:
    """Public endpoint returning OAuth 2.0 Protected Resource Metadata."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "resource": f"{base_url}/mcp",
        "authorization_servers": [base_url],
        "scopes_supported": ["purchase"],
        "bearer_methods_supported": ["header"],
    }


# -----------------------------------------------------------------------------
# Authorization & Login Endpoints
# -----------------------------------------------------------------------------
@router.get(
    "/oauth/authorize",
    response_class=HTMLResponse,
    summary="OAuth 2.1 Authorization Form",
    description="Renders the customer authorization login form."
)
def get_authorize_page(
    response_type: str = Query(default="code"),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default="purchase"),
):
    """Renders HTML login form for customer authentication."""
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported response_type. Must be 'code'."
        )
    if client_id != OAUTH_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid client_id: '{client_id}'."
        )
    if not is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unauthorized redirect_uri: '{redirect_uri}'."
        )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Agentic Gateway — Customer Authorization</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .card {{ background: #1e293b; padding: 2rem; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); width: 360px; }}
        h2 {{ margin-top: 0; color: #38bdf8; font-size: 1.4rem; }}
        p {{ color: #94a3b8; font-size: 0.9rem; }}
        label {{ display: block; margin-top: 1rem; color: #cbd5e1; font-size: 0.85rem; }}
        input {{ width: 100%; padding: 0.6rem; margin-top: 0.3rem; border: 1px solid #334155; border-radius: 6px; background: #0f172a; color: #f8fafc; box-sizing: border-box; }}
        button {{ width: 100%; padding: 0.75rem; margin-top: 1.5rem; background: #3b82f6; border: none; border-radius: 6px; color: white; font-weight: 600; cursor: pointer; }}
        button:hover {{ background: #2563eb; }}
        .demo-note {{ margin-top: 1rem; padding: 0.6rem; background: #334155; border-radius: 6px; font-size: 0.8rem; color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Authorize AI Shopping Agent</h2>
        <p>Log in with your customer account to authorize Claude to propose purchases within your mandate.</p>
        <form method="POST" action="/oauth/authorize">
            <input type="hidden" name="client_id" value="{client_id}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="response_type" value="{response_type}">
            <input type="hidden" name="state" value="{state or ''}">
            <input type="hidden" name="scope" value="{scope or 'purchase'}">
            
            <label>Username / Email</label>
            <input type="text" name="username" placeholder="e.g. dinesh or dinesh@example.com" required autofocus>
            
            <label>Password</label>
            <input type="password" name="password" placeholder="••••••••" required>
            
            <button type="submit">Authorize Access</button>
        </form>
        <div class="demo-note">
            Demo credentials: <strong>dinesh</strong> / <strong>password123</strong> (CUST001) or <strong>alex</strong> / <strong>password123</strong> (CUST002)
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.post(
    "/oauth/authorize",
    summary="Process customer login and issue authorization code",
)
async def post_authorize(
    request: Request,
    username: Optional[str] = Form(default=None),
    password: Optional[str] = Form(default=None),
    client_id: Optional[str] = Form(default=None),
    redirect_uri: Optional[str] = Form(default=None),
    response_type: Optional[str] = Form(default="code"),
    state: Optional[str] = Form(default=None),
    scope: Optional[str] = Form(default="purchase"),
):
    """Processes login credentials and returns redirect with authorization code."""
    # Check if JSON payload was sent instead of Form
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        username = body.get("username", username)
        password = body.get("password", password)
        client_id = body.get("client_id", client_id)
        redirect_uri = body.get("redirect_uri", redirect_uri)
        response_type = body.get("response_type", response_type)
        state = body.get("state", state)
        scope = body.get("scope", scope)

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required."
        )
    if client_id != OAUTH_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_id."
        )
    if not is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unauthorized redirect_uri."
        )

    customer_id = customer_auth_store.authenticate(username, password)
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password."
        )

    # Issue authorization code
    code = auth_code_store.issue_code(
        customer_id=customer_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope or "purchase",
    )

    query_params = {"code": code}
    if state:
        query_params["state"] = state

    target_url = f"{redirect_uri}?{urlencode(query_params)}"

    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse(content={"redirect_uri": target_url, "code": code, "state": state})

    return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)


# -----------------------------------------------------------------------------
# Token Issuance & Refresh Endpoint
# -----------------------------------------------------------------------------
@router.post(
    "/oauth/token",
    response_model=TokenResponse,
    summary="Issue or refresh access token",
)
async def post_token(
    request: Request,
    grant_type: Optional[str] = Form(default=None),
    code: Optional[str] = Form(default=None),
    redirect_uri: Optional[str] = Form(default=None),
    refresh_token: Optional[str] = Form(default=None),
    client_id: Optional[str] = Form(default=None),
    client_secret: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """
    Exchanges an authorization code or refresh token for a signed JWT access token bound to customer_id.
    """
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        grant_type = body.get("grant_type", grant_type)
        code = body.get("code", code)
        redirect_uri = body.get("redirect_uri", redirect_uri)
        refresh_token = body.get("refresh_token", refresh_token)
        client_id = body.get("client_id", client_id)
        client_secret = body.get("client_secret", client_secret)

    if not _validate_client_credentials(client_id, client_secret, authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials."
        )

    effective_client_id = client_id or OAUTH_CLIENT_ID

    # 1. Authorization Code Grant
    if grant_type == "authorization_code":
        if not code or not redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code and redirect_uri are required for authorization_code grant."
            )

        customer_id = auth_code_store.consume_code(
            code=code,
            client_id=effective_client_id,
            redirect_uri=redirect_uri,
        )

        if not customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or previously used authorization code."
            )

        access_token = create_access_token(customer_id=customer_id)
        issued_refresh_token = customer_auth_store.issue_refresh_token(
            customer_id=customer_id,
            client_id=effective_client_id,
            ttl_days=30,
        )

        return TokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=issued_refresh_token,
            scope="purchase",
        )

    # 2. Refresh Token Grant (with Refresh Token Rotation)
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="refresh_token is required for refresh_token grant."
            )

        rotation_result = customer_auth_store.rotate_refresh_token(
            raw_refresh_token=refresh_token,
            client_id=effective_client_id,
            ttl_days=30,
        )

        if rotation_result is None:
            # Generic error to prevent information leakage
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or revoked refresh token."
            )

        customer_id, new_rotated_refresh_token = rotation_result
        new_access_token = create_access_token(customer_id=customer_id)

        return TokenResponse(
            access_token=new_access_token,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=new_rotated_refresh_token,
            scope="purchase",
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported grant_type '{grant_type}'. Supported grant types: 'authorization_code', 'refresh_token'."
        )

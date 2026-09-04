import base64
import html
import json
import os
from typing import Any, List, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from pydantic import BaseModel, Field
from app.policy.store import mandate_store
from app.oauth.crypto import create_access_token
from app.oauth.models import TokenRequest, TokenResponse
from app.oauth.store import (
    ALLOWED_REDIRECT_URIS,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    auth_code_store,
    customer_auth_store,
    is_allowed_client_id,
    is_allowed_redirect_uri,
    provision_new_customer,
    register_dynamic_client,
)

router = APIRouter(tags=["oauth"])


def _validate_client_credentials(
    client_id: Optional[str],
    client_secret: Optional[str],
    auth_header: Optional[str] = None,
    code_verifier: Optional[str] = None,
    code_record: Optional[Any] = None,
) -> bool:
    """Validates client_id and client_secret from body, Authorization: Basic header, or PKCE public client."""
    effective_client_id = client_id or OAUTH_CLIENT_ID

    # 1. Check Basic Auth header
    if auth_header and auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            h_client_id, h_client_secret = decoded.split(":", 1)
            return is_allowed_client_id(h_client_id) and h_client_secret == OAUTH_CLIENT_SECRET
        except Exception:
            return False

    # 2. Check secret provided in body
    if client_secret:
        return is_allowed_client_id(effective_client_id) and client_secret == OAUTH_CLIENT_SECRET

    # 3. PKCE Public Client (No client_secret required per RFC 7636 / RFC 6749)
    if code_verifier and code_record and code_record.code_challenge:
        return is_allowed_client_id(effective_client_id)

    return False


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
        "registration_endpoint": f"{base_url}/oauth/register-client",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic", "none"],
        "scopes_supported": ["purchase"],
        "code_challenge_methods_supported": ["S256"],
    }


class DynamicClientRegistrationRequest(BaseModel):
    client_name: Optional[str] = "ChatGPT Connector"
    redirect_uris: Optional[list] = None
    grant_types: Optional[list] = ["authorization_code", "refresh_token"]
    response_types: Optional[list] = ["code"]
    token_endpoint_auth_method: Optional[str] = "none"


@router.post(
    "/oauth/register-client",
    status_code=status.HTTP_201_CREATED,
    summary="Dynamic Client Registration (RFC 7591)",
    description="Registers an OAuth client dynamically and returns client credentials."
)
async def register_oauth_client(request: Request):
    """RFC 7591 Dynamic Client Registration endpoint."""
    import secrets
    import time
    body = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except Exception:
            body = {}

    client_id = f"client_{secrets.token_urlsafe(16)}"
    client_secret = secrets.token_urlsafe(32)
    redirect_uris = body.get("redirect_uris") or []

    register_dynamic_client(client_id, client_secret, redirect_uris)

    return JSONResponse(
        status_code=201,
        content={
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": body.get("client_name", "ChatGPT Connector"),
            "redirect_uris": redirect_uris,
            "grant_types": body.get("grant_types", ["authorization_code", "refresh_token"]),
            "response_types": body.get("response_types", ["code"]),
            "token_endpoint_auth_method": body.get("token_endpoint_auth_method", "none"),
            "client_id_issued_at": int(time.time()),
        }
    )


@router.get(
    "/.well-known/openid-configuration",
    summary="OpenID Connect / OAuth Discovery Metadata",
    description="Alias discovery endpoint for clients that query openid-configuration."
)
def get_openid_configuration(request: Request) -> dict:
    """Returns OAuth 2.0 Authorization Server Metadata as OpenID configuration alias."""
    return get_oauth_authorization_server_metadata(request)


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
# Authorization, Registration & SSO Endpoints
# -----------------------------------------------------------------------------
@router.get(
    "/oauth/authorize",
    response_class=HTMLResponse,
    summary="OAuth 2.1 Authorization Form",
    description="Renders the customer authorization login and registration form."
)
def get_authorize_page(
    response_type: str = Query(default="code"),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default="purchase"),
    code_challenge: Optional[str] = Query(default=None),
    code_challenge_method: Optional[str] = Query(default=None),
):
    """Renders HTML login & sign-up form with Google SSO for customer authentication."""
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported response_type. Must be 'code'."
        )
    if not is_allowed_client_id(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid client_id: '{client_id}'."
        )
    if not is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unauthorized redirect_uri: '{redirect_uri}'."
        )

    google_params_dict = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state or "",
        "scope": scope or "purchase",
    }
    if code_challenge:
        google_params_dict["code_challenge"] = code_challenge
    if code_challenge_method:
        google_params_dict["code_challenge_method"] = code_challenge_method

    google_login_params = urlencode(google_params_dict)
    google_login_url = f"/oauth/google/login?{google_login_params}"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorize AI Shopping Agent — Agentic Gateway</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #F8FAFC;
            color: #0F172A;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 1.5rem;
        }}
        .card {{
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 18px;
            box-shadow: 0 10px 25px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -2px rgba(15, 23, 42, 0.04);
            width: 100%;
            max-width: 420px;
            padding: 2.2rem;
            animation: fadeIn 0.3s ease-out;
        }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .header {{ text-align: center; margin-bottom: 1.6rem; }}
        .logo-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            border-radius: 12px;
            background: linear-gradient(135deg, #4F46E5, #2563EB);
            margin-bottom: 0.8rem;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
        }}
        h2 {{ color: #0F172A; font-size: 1.4rem; font-weight: 800; letter-spacing: -0.02em; }}
        .subtitle {{ color: #64748B; font-size: 0.88rem; margin-top: 0.3rem; line-height: 1.4; }}
        
        .btn-google {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            width: 100%;
            padding: 0.75rem 1rem;
            background: #FFFFFF;
            color: #0F172A;
            font-size: 0.92rem;
            font-weight: 600;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            text-decoration: none;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
            margin-bottom: 1.4rem;
        }}
        .btn-google:hover {{
            background: #F8FAFC;
            border-color: #CBD5E1;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        }}
        
        .divider {{
            display: flex;
            align-items: center;
            text-align: center;
            margin: 1.2rem 0;
            color: #64748B;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .divider::before, .divider::after {{
            content: '';
            flex: 1;
            border-bottom: 1px solid #E2E8F0;
        }}
        .divider span {{ padding: 0 0.8rem; }}
        
        .tabs {{
            display: flex;
            background: #F1F5F9;
            border-radius: 10px;
            padding: 4px;
            margin-bottom: 1.4rem;
            border: 1px solid #E2E8F0;
        }}
        .tab-btn {{
            flex: 1;
            padding: 0.5rem;
            background: transparent;
            border: none;
            color: #64748B;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .tab-btn.active {{
            background: #4F46E5;
            color: #FFFFFF;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.25);
        }}
        
        .form-group {{ margin-bottom: 1rem; }}
        label {{ display: block; margin-bottom: 0.35rem; color: #0F172A; font-size: 0.82rem; font-weight: 600; }}
        input[type="text"], input[type="email"], input[type="password"] {{
            width: 100%;
            padding: 0.65rem 0.85rem;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            background: #FFFFFF;
            color: #0F172A;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }}
        input:focus {{
            border-color: #4F46E5;
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
        }}
        
        .btn-submit {{
            width: 100%;
            padding: 0.75rem;
            background: #4F46E5;
            border: none;
            border-radius: 9px;
            color: white;
            font-size: 0.92rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 4px 14px rgba(79, 70, 229, 0.25);
            margin-top: 0.5rem;
        }}
        .btn-submit:hover {{
            background: #4338CA;
            transform: translateY(-1px);
        }}
        
        .info-pill {{
            margin-top: 1.2rem;
            padding: 0.7rem 0.9rem;
            background: #F8FAFC;
            border: 1px dashed #CBD5E1;
            border-radius: 8px;
            font-size: 0.78rem;
            color: #64748B;
            line-height: 1.4;
        }}
        .info-pill strong {{ color: #0F172A; }}
        .badge-mandate {{ color: #4F46E5; font-weight: 700; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <div class="logo-badge">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
            </div>
            <h2>Authorize AI Shopping Agent</h2>
            <p class="subtitle">Connect Claude to transact securely under your bounded spending mandate.</p>
        </div>

        <!-- Google OAuth SSO Button -->
        <a href="{google_login_url}" class="btn-google">
            <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"/>
                <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.35 24 12 24z"/>
                <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.98 0 12s.45 3.82 1.25 5.42l4.03-3.15z"/>
                <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.35 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"/>
            </svg>
            Continue with Google
        </a>

        <div class="divider"><span>or with credentials</span></div>

        <!-- Tabs -->
        <div class="tabs">
            <button type="button" class="tab-btn active" id="tab-login" onclick="switchTab('login')">Sign In</button>
            <button type="button" class="tab-btn" id="tab-signup" onclick="switchTab('signup')">Create Account</button>
        </div>

        <!-- Sign In Form -->
        <form id="form-login" method="POST" action="/oauth/authorize">
            <input type="hidden" name="client_id" value="{client_id}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="response_type" value="{response_type}">
            <input type="hidden" name="state" value="{state or ''}">
            <input type="hidden" name="scope" value="{scope or 'purchase'}">
            <input type="hidden" name="code_challenge" value="{code_challenge or ''}">
            <input type="hidden" name="code_challenge_method" value="{code_challenge_method or ''}">

            <div class="form-group">
                <label>Username or Email</label>
                <input type="text" name="username" placeholder="dinesh or dinesh@example.com" required autofocus>
            </div>

            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" placeholder="••••••••" required>
            </div>

            <button type="submit" class="btn-submit">Authorize Access</button>
        </form>

        <!-- Sign Up / Register Form -->
        <form id="form-signup" method="POST" action="/oauth/register" style="display: none;">
            <input type="hidden" name="client_id" value="{client_id}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="response_type" value="{response_type}">
            <input type="hidden" name="state" value="{state or ''}">
            <input type="hidden" name="scope" value="{scope or 'purchase'}">
            <input type="hidden" name="code_challenge" value="{code_challenge or ''}">
            <input type="hidden" name="code_challenge_method" value="{code_challenge_method or ''}">

            <div class="form-group">
                <label>Full Name</label>
                <input type="text" name="display_name" placeholder="John Doe" required>
            </div>

            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" placeholder="johndoe" required>
            </div>

            <div class="form-group">
                <label>Email Address</label>
                <input type="email" name="email" placeholder="john@example.com" required>
            </div>

            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" placeholder="••••••••" required>
            </div>

            <div class="form-group">
                <label>AI Agent Spending Limit (₹ INR)</label>
                <input type="number" name="mandate_limit" value="2000" min="100" max="100000" step="100" placeholder="2000" required>
            </div>

            <button type="submit" class="btn-submit">Create Account & Authorize</button>
        </form>

        <div class="info-pill" id="login-demo-pill">
            Demo Credentials: <strong>dinesh</strong> / <strong>password123</strong> (CUST001) or <strong>alex</strong> / <strong>password123</strong> (CUST002).
        </div>
        <div class="info-pill" id="signup-info-pill" style="display: none;">
            ✨ You control your agent's budget. Set your initial limit above, and adjust it anytime directly in conversation with your AI buyer.
        </div>
    </div>

    <script>
        function switchTab(tab) {{
            const loginBtn = document.getElementById('tab-login');
            const signupBtn = document.getElementById('tab-signup');
            const loginForm = document.getElementById('form-login');
            const signupForm = document.getElementById('form-signup');
            const loginPill = document.getElementById('login-demo-pill');
            const signupPill = document.getElementById('signup-info-pill');

            if (tab === 'login') {{
                loginBtn.classList.add('active');
                signupBtn.classList.remove('active');
                loginForm.style.display = 'block';
                signupForm.style.display = 'none';
                loginPill.style.display = 'block';
                signupPill.style.display = 'none';
            }} else {{
                signupBtn.classList.add('active');
                loginBtn.classList.remove('active');
                signupForm.style.display = 'block';
                loginForm.style.display = 'none';
                signupPill.style.display = 'block';
                loginPill.style.display = 'none';
            }}
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get(
    "/oauth/google/login",
    summary="Initiate Google OAuth 2.0 SSO",
    description="Redirects user to Google OAuth 2.0 authorization page while preserving original MCP client state."
)
def google_login(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default="purchase"),
    code_challenge: Optional[str] = Query(default=None),
    code_challenge_method: Optional[str] = Query(default=None),
):
    """Generates Google OAuth URL and redirects browser to Google Sign-In."""
    if not is_allowed_client_id(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_id."
        )
    if not is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unauthorized redirect_uri: '{redirect_uri}'."
        )

    # Pack client state into JSON base64 string
    state_payload = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope or "purchase",
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

    google_params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": encoded_state,
        "access_type": "online",
        "prompt": "select_account",
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(google_params)}"
    return RedirectResponse(url=google_auth_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/oauth/google/callback",
    summary="Handle Google OAuth 2.0 Callback",
    description="Exchanges Google auth code for profile, auto-provisions or resolves customer, and redirects to MCP client."
)
async def google_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Processes callback from Google OAuth, logs in / registers customer, and returns Gateway authorization code."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authentication error: {error}"
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code or state from Google."
        )

    import logging
    logger = logging.getLogger("gateway.oauth")

    try:
        # Unpack state
        try:
            decoded_state_json = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
            state_data = json.loads(decoded_state_json)
            client_id = state_data["client_id"]
            redirect_uri = state_data["redirect_uri"]
            client_state = state_data.get("state")
            client_scope = state_data.get("scope", "purchase")
            client_code_challenge = state_data.get("code_challenge")
            client_code_challenge_method = state_data.get("code_challenge_method")
        except Exception as e:
            logger.error("Failed to decode Google OAuth state parameter: %s", e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or malformed state parameter."
            )

        client_id_val = os.getenv("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
        client_secret_val = os.getenv("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
        redirect_uri_val = os.getenv("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI)

        # Exchange code for Google ID token / access token
        async with httpx.AsyncClient() as http_client:
            token_res = await http_client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id_val,
                    "client_secret": client_secret_val,
                    "redirect_uri": redirect_uri_val,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            if token_res.status_code != 200:
                logger.error("Google token exchange failed (%s): %s", token_res.status_code, token_res.text)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange token with Google: {token_res.text}"
                )

            token_json = token_res.json()
            google_access_token = token_json.get("access_token")
            if not google_access_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No access token returned by Google."
                )

            # Fetch Google user profile
            userinfo_res = await http_client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {google_access_token}"},
                timeout=15.0,
            )
            if userinfo_res.status_code != 200:
                logger.error("Google userinfo fetch failed (%s): %s", userinfo_res.status_code, userinfo_res.text)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch Google user profile."
                )

            userinfo = userinfo_res.json()
            email = userinfo.get("email")
            name = userinfo.get("name") or (email.split("@")[0] if email else "Google User")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google profile did not provide an email address."
            )

        # Check if customer already exists, otherwise auto-provision
        existing_user = customer_auth_store.get_user_by_email(email)
        if existing_user:
            customer_id = existing_user.customer_id
        else:
            customer_id, _ = provision_new_customer(
                display_name=name,
                email=email,
                initial_budget=2000.0,
            )

        # Issue gateway authorization code
        auth_code = auth_code_store.issue_code(
            customer_id=customer_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=client_scope or "purchase",
            code_challenge=client_code_challenge,
            code_challenge_method=client_code_challenge_method,
        )

        query_params = {"code": auth_code}
        if client_state:
            query_params["state"] = client_state

        target_url = f"{redirect_uri}?{urlencode(query_params)}"
        return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in google_callback: %s", e, exc_info=True)
        return HTMLResponse(
            f"""<!DOCTYPE html><html><body style="font-family:'Inter',sans-serif;background:#F8FAFC;color:#0F172A;padding:40px;">
            <h2>Google Sign-In Error</h2><p style="color:#DC2626;">{html.escape(str(e))}</p>
            <p><a href="/oauth/authorize?client_id=claude-desktop-client" style="color:#4F46E5;">Return to Sign In</a></p>
            </body></html>""",
            status_code=500
        )


@router.post(
    "/oauth/register",
    summary="Self-service customer registration and authorization",
    description="Registers a new customer account, provisions a default spending mandate, and issues an authorization code."
)
async def post_register(
    request: Request,
    display_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: Optional[str] = Form(default="code"),
    state: Optional[str] = Form(default=None),
    scope: Optional[str] = Form(default="purchase"),
    mandate_limit: Optional[float] = Form(default=2000.0),
    code_challenge: Optional[str] = Form(default=None),
    code_challenge_method: Optional[str] = Form(default=None),
):
    """Processes self-service registration and returns redirect with authorization code."""
    if not is_allowed_client_id(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid client_id: '{client_id}'."
        )
    if not is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unauthorized redirect_uri: '{redirect_uri}'."
        )

    clean_user = username.strip().lower()
    clean_email = email.strip().lower()

    if customer_auth_store.get_user_by_username(clean_user) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{clean_user}' is already taken."
        )
    if customer_auth_store.get_user_by_email(clean_email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{clean_email}' is already registered."
        )

    budget = float(mandate_limit) if mandate_limit and float(mandate_limit) > 0 else 2000.0
    try:
        customer_id, _ = provision_new_customer(
            display_name=display_name.strip(),
            username=clean_user,
            email=clean_email,
            password=password,
            initial_budget=budget,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    code = auth_code_store.issue_code(
        customer_id=customer_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope or "purchase",
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    query_params = {"code": code}
    if state:
        query_params["state"] = state

    target_url = f"{redirect_uri}?{urlencode(query_params)}"
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse(content={
            "redirect_uri": target_url,
            "code": code,
            "state": state,
            "customer_id": customer_id
        })

    return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)


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
    code_challenge: Optional[str] = Form(default=None),
    code_challenge_method: Optional[str] = Form(default=None),
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
        code_challenge = body.get("code_challenge", code_challenge)
        code_challenge_method = body.get("code_challenge_method", code_challenge_method)

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required."
        )
    if not is_allowed_client_id(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid client_id: '{client_id}'."
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
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
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
    code_verifier: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """
    Exchanges an authorization code or refresh token for a signed JWT access token bound to customer_id.
    Supports RFC 7636 PKCE (code_verifier).
    """
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        grant_type = body.get("grant_type", grant_type)
        code = body.get("code", code)
        redirect_uri = body.get("redirect_uri", redirect_uri)
        refresh_token = body.get("refresh_token", refresh_token)
        client_id = body.get("client_id", client_id)
        client_secret = body.get("client_secret", client_secret)
        code_verifier = body.get("code_verifier", code_verifier)

    effective_client_id = client_id or OAUTH_CLIENT_ID
    code_record = auth_code_store.get_code_record(code) if code else None

    if not _validate_client_credentials(
        client_id=effective_client_id,
        client_secret=client_secret,
        auth_header=authorization,
        code_verifier=code_verifier,
        code_record=code_record,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials."
        )

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
            code_verifier=code_verifier,
        )

        if not customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or previously used authorization code (or invalid PKCE code_verifier)."
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


class CustomerMandateUpdateRequest(BaseModel):
    username_or_email: str = Field(..., description="Customer username or email")
    password: str = Field(..., description="Customer account password")
    new_limit: float = Field(..., description="Desired new per-transaction spending limit in INR", gt=0)


@router.get("/customer/mandate-info", summary="Customer self-service mandate inquiry")
def get_customer_mandate_info(identifier: str):
    """
    Returns mandate details for a customer identifier so the customer can view their limits.
    """
    clean_id = identifier.strip()
    cust_id = None
    user = customer_auth_store.get_user_by_username(clean_id.lower())
    if user:
        cust_id = user.customer_id
    else:
        user_email = customer_auth_store.get_user_by_email(clean_id.lower())
        if user_email:
            cust_id = user_email.customer_id
        else:
            matches = mandate_store.find_by_identifier(clean_id)
            if matches:
                cust_id = matches[0].customer_id

    if not cust_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{identifier}' not found."
        )

    mandate = mandate_store.get_mandate(cust_id)
    if not mandate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mandate for customer '{cust_id}' not found."
        )

    return {
        "customer_id": mandate.customer_id,
        "display_name": mandate.display_name,
        "email": mandate.email,
        "mandate_limit": mandate.max_transaction_amount,
        "allowed_categories": mandate.allowed_categories,
        "allowed_merchants": mandate.allowed_merchants,
        "expires_at": mandate.expires_at,
        "prompt_playback": mandate.prompt_playback,
    }


@router.post("/customer/mandate/update", summary="Customer self-service mandate limit update")
def update_customer_mandate_self(payload: CustomerMandateUpdateRequest):
    """
    Allows a verified customer to modify their own AI agent spending mandate limit.
    Requires customer credentials for Zero-Trust authorization.
    """
    clean_id = payload.username_or_email.strip()
    cust_id = customer_auth_store.authenticate(clean_id, payload.password)
    if not cust_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password."
        )

    if payload.new_limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandate limit must be greater than zero."
        )

    if payload.new_limit > 100000.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum allowable personal mandate limit is ₹1,00,000.00."
        )

    updated_mandate = mandate_store.update_mandate_limit(
        customer_id=cust_id,
        new_limit=payload.new_limit,
    )

    return {
        "status": "success",
        "customer_id": cust_id,
        "display_name": updated_mandate.display_name,
        "new_limit": updated_mandate.max_transaction_amount,
        "message": f"Successfully updated your spending limit to ₹{updated_mandate.max_transaction_amount:,.2f}.",
    }


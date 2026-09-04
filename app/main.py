import logging
import os
from dotenv import load_dotenv

# Load .env into the process environment before any SDK clients are instantiated.
# override=False: real environment variables always win over .env values.
load_dotenv(override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.admin.router import router as admin_router
from app.agent.router import router as agent_router
from app.audit import audit_router
from app.catalog.router import router as catalog_router
from app.mcp.server import mount_remote_mcp, remote_mcp_lifespan
from app.merchant_agent import merchant_agent_router
from app.oauth.router import router as oauth_router
from app.payment.router import router as payment_router

app = FastAPI(
    title="Agentic Commerce Gateway",
    description="Merchant-side gateway enabling AI shopping agents to transact under bounded, auditable policy mandates.",
    version="1.0.0",
    lifespan=remote_mcp_lifespan,
)

class McpNormalizeMiddleware:
    """
    Normalizes /mcp requests:
    1. Prevents 307 Temporary Redirect for /mcp without trailing slash by rewriting path to /mcp/.
    2. Ensures Accept header includes text/event-stream so standard HTTP clients (like ChatGPT)
       receive JSON-RPC responses without 406 Not Acceptable errors.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            raw_path = scope.get("path", "")
            if raw_path == "/mcp" or raw_path == "/mcp/":
                scope = dict(scope)
                scope["path"] = "/mcp/"
                headers = dict(scope.get("headers", []))
                accept = headers.get(b"accept", b"")
                if b"text/event-stream" not in accept:
                    new_headers = []
                    found_accept = False
                    for k, v in scope.get("headers", []):
                        if k.lower() == b"accept":
                            found_accept = True
                            new_val = v + b", text/event-stream" if v else b"application/json, text/event-stream"
                            new_headers.append((k, new_val))
                        else:
                            new_headers.append((k, v))
                    if not found_accept:
                        new_headers.append((b"accept", b"application/json, text/event-stream"))
                    scope["headers"] = new_headers
        await self.app(scope, receive, send)


# Enable CORS for ChatGPT and web MCP clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(McpNormalizeMiddleware)

# Mount static files directory if it exists
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount REST, OAuth, and Merchant Agent routers
app.include_router(catalog_router)
app.include_router(agent_router)
app.include_router(audit_router)
app.include_router(admin_router)
app.include_router(oauth_router)
app.include_router(merchant_agent_router)
app.include_router(payment_router)

# Mount remote Streamable HTTP MCP server at /mcp
mount_remote_mcp(app, path="/mcp")


@app.get("/admin/dashboard", tags=["admin"], summary="Admin Web Dashboard UI")
def get_admin_dashboard():
    """Serves the interactive Admin Web Dashboard HTML application."""
    html_path = os.path.join(static_dir, "admin", "index.html")
    return FileResponse(
        html_path,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/checkout", tags=["payment"], summary="User Self-Checkout UI")
def get_checkout_page():
    """Serves the standalone Razorpay self-checkout page."""
    html_path = os.path.join(static_dir, "checkout", "index.html")
    return FileResponse(html_path)


@app.get("/admin", tags=["admin"], summary="Admin Web Dashboard Redirect")
def redirect_to_dashboard():
    """Redirects /admin to the Admin Web Dashboard."""
    return RedirectResponse(url="/admin/dashboard")


@app.get("/health", tags=["system"], summary="Health check endpoint")
def health_check() -> dict:
    """
    Returns the operational status of the gateway services.
    """
    return {
        "status": "healthy",
        "service": "gateway",
        "version": "1.0.0"
    }

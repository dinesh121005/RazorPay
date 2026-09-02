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

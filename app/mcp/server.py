"""
Model Context Protocol (MCP) server entrypoint and remote Streamable HTTP application.

Supports:
1. Local stdio transport (python -m app.mcp.server) for single-user local Claude Desktop usage.
2. Remote Streamable HTTP transport mounted at /mcp on the FastAPI application with OAuth Bearer authentication.
"""
from typing import Optional
from dotenv import load_dotenv

# Ensure environment variables (.env) are loaded before server starts
load_dotenv(override=False)

import jwt
from fastapi import FastAPI
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        try:
            from mcp.server import MCPServer
        except ImportError:
            from mcp.server import FastMCP as MCPServer
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.mcp.tools import (
    authenticated_customer_id,
    register_remote_tools,
    register_tools,
)
from app.oauth.crypto import verify_access_token


class McpAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware enforcing valid OAuth 2.1 JWT Bearer token authentication on all remote MCP requests.
    Extracts customer_id from token's `sub` claim and binds it to contextvars.
    """
    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        base_auth_header = {
            "WWW-Authenticate": (
                'Bearer realm="ai-buyer-gateway", '
                'resource_metadata="/.well-known/oauth-protected-resource", '
                'as_uri="/.well-known/oauth-authorization-server"'
            )
        }

        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                headers=base_auth_header,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": "Unauthorized: Missing or malformed Bearer token in Authorization header."
                    }
                }
            )

        token = auth_header[7:].strip()
        try:
            payload = verify_access_token(token)
            customer_id = payload.get("sub")
            if not customer_id:
                return JSONResponse(
                    status_code=401,
                    headers=base_auth_header,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32001,
                            "message": "Unauthorized: Access token missing 'sub' claim."
                        }
                    }
                )
            
            # Bind verified customer_id to async request context
            token_reset = authenticated_customer_id.set(customer_id)
            try:
                response = await call_next(request)
                return response
            finally:
                authenticated_customer_id.reset(token_reset)

        except jwt.ExpiredSignatureError:
            expired_headers = {
                "WWW-Authenticate": (
                    'Bearer realm="ai-buyer-gateway", error="invalid_token", '
                    'error_description="The access token expired", '
                    'resource_metadata="/.well-known/oauth-protected-resource", '
                    'as_uri="/.well-known/oauth-authorization-server"'
                )
            }
            return JSONResponse(
                status_code=401,
                headers=expired_headers,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": "Unauthorized: Access token has expired."
                    }
                }
            )
        except jwt.PyJWTError as e:
            invalid_headers = {
                "WWW-Authenticate": (
                    f'Bearer realm="ai-buyer-gateway", error="invalid_token", '
                    f'error_description="{str(e)}", '
                    'resource_metadata="/.well-known/oauth-protected-resource", '
                    'as_uri="/.well-known/oauth-authorization-server"'
                )
            }
            return JSONResponse(
                status_code=401,
                headers=invalid_headers,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": f"Unauthorized: Invalid access token ({str(e)})."
                    }
                }
            )


def create_mcp_server() -> MCPServer:
    """
    Factory initializing local stdio MCP server instance with full demo tool set.
    """
    server = MCPServer(
        name="ai-buyer-gateway",
        instructions=(
            "ai-buyer-gateway enables secure, policy-gated Agent-to-Agent (A2A) commerce. "
            "You are the Buyer AI Agent acting on behalf of the customer under a deterministic spending mandate. "
            "Safety & Gating Architecture: "
            "1. Inquire: Call `inquire_merchant` (or `search_products`) to obtain transparent product quotes and stock availability. "
            "2. Propose: Call `propose_purchase` with the selected product_id and customer_id='CUST001'. An AI agent may propose, never unilaterally authorize. "
            "3. Gated Confirmation: If the proposal returns `requires_confirmation: true` (for orders >= ₹500), present the quote breakdown to the user. "
            "   When the user approves, call `confirm_purchase` with the `confirmation_token` to execute payment. "
            "4. Revenue Growth: Call `suggest_addons` to discover complementary merchant add-ons within the user's remaining mandate budget."
        ),
    )
    register_tools(server)
    return server


def create_remote_mcp_server() -> MCPServer:
    """
    Factory initializing remote OAuth-authenticated MCP server instance.
    `propose_purchase` accepts ONLY product_id and quantity — identity is bound from JWT.
    """
    server = MCPServer(
        name="ai-buyer-gateway-remote",
        instructions=(
            "ai-buyer-gateway enables secure, policy-gated Agent-to-Agent (A2A) commerce. "
            "You are the Buyer AI Agent acting on behalf of the authenticated customer under a deterministic spending mandate. "
            "Safety & Gating Architecture: "
            "1. Inquire: Call `inquire_merchant` to obtain product quotes and recommendations from the store's Merchant Sales Agent. "
            "2. Propose: Call `propose_purchase` with the selected product_id and quantity. "
            "3. Gated Confirmation: For purchases >= ₹500, `propose_purchase` returns `requires_confirmation: true` and a `confirmation_token`. "
            "   Show the quote breakdown to the user, and execute `confirm_purchase` once confirmed. "
            "4. Revenue Growth: Call `suggest_addons` to discover complementary merchant add-ons within the user's remaining budget headroom."
        ),
    )
    register_remote_tools(server)
    return server



from contextlib import asynccontextmanager
from mcp.server.transport_security import TransportSecuritySettings


# Remote MCP Server Singleton & Streamable App
remote_mcp_server = create_remote_mcp_server()
_transport_sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
_streamable_asgi = remote_mcp_server.streamable_http_app(
    streamable_http_path="/",
    transport_security=_transport_sec,
    stateless_http=True,
)


@asynccontextmanager
async def remote_mcp_lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager initializing the MCP StreamableHTTP session task group.
    """
    async with remote_mcp_server._lowlevel_server._session_manager.run():
        yield


def get_remote_mcp_app() -> Starlette:
    """
    Builds the Starlette ASGI application for Streamable HTTP transport with OAuth authentication middleware.
    """
    app = Starlette(routes=_streamable_asgi.routes)
    app.add_middleware(McpAuthMiddleware)
    return app


# Local stdio server singleton for stdio runner
mcp_server = create_mcp_server()


def mount_remote_mcp(fastapi_app: FastAPI, path: str = "/mcp") -> None:
    """
    Mounts the authenticated remote Streamable HTTP MCP server on the FastAPI application.
    """
    mcp_app = get_remote_mcp_app()
    fastapi_app.mount(path, mcp_app)


def main() -> None:
    """
    Entrypoint when executed as a module: python -m app.mcp.server
    Runs the stdio transport event loop for local Claude Desktop.
    """
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()

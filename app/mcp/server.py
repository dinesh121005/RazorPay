"""
Model Context Protocol (MCP) server entrypoint for ai-buyer-gateway.

Runs over stdio transport, enabling MCP-aware AI clients (such as Claude Desktop)
to natively invoke the gateway's propose_purchase tool.
"""
from dotenv import load_dotenv

# Ensure environment variables (.env) are loaded before server starts
load_dotenv(override=False)

from mcp.server.mcpserver import MCPServer
from app.mcp.tools import register_tools


def create_mcp_server() -> MCPServer:
    """
    Factory function initializing the MCP server and registering all gateway tools.
    """
    server = MCPServer(
        name="ai-buyer-gateway",
        instructions=(
            "ai-buyer-gateway enables AI shopping agents to propose purchases under "
            "deterministic customer spending mandates with real-time Razorpay Test Mode execution."
        ),
    )
    register_tools(server)
    return server


# Module-level server instance
mcp_server = create_mcp_server()


def main() -> None:
    """
    Entrypoint when executed as a module: python -m app.mcp.server
    Runs the stdio transport event loop for Claude Desktop.
    """
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()

"""
MCP tool definitions and handlers for ai-buyer-gateway.

Exposes the `propose_purchase` tool to AI clients (e.g. Claude Desktop) over stdio.
The tool delegates directly to app.agent.service.execute_purchase() — maintaining
zero duplication of business logic or policy orchestration.
"""
from typing import Any, Dict
from mcp.server.mcpserver import MCPServer

from app.agent.service import execute_purchase


def propose_purchase_handler(
    customer_id: str,
    product_id: str,
    quantity: int = 1,
) -> Dict[str, Any]:
    """
    Core handler executing a purchase proposal through the gateway.
    Returns serialized PurchaseResponse dict.
    """
    response = execute_purchase(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
    )
    return response.model_dump()


def register_tools(server: MCPServer) -> None:
    """
    Registers gateway tools with the MCP server instance.
    """
    @server.tool(
        name="propose_purchase",
        description=(
            "Propose an agent purchase transaction under customer mandate rules. "
            "The gateway evaluates deterministic policy rules (budget limit, merchant, "
            "category, expiration) and creates a Razorpay Test Mode order ONLY if approved. "
            "An agent may only propose, never authorize."
        )
    )
    def propose_purchase(
        customer_id: str,
        product_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Propose a purchase on behalf of a customer.

        Args:
            customer_id: Unique customer identifier with an authorized mandate (e.g. 'CUST001').
            product_id: Product ID from the catalog to purchase (e.g. 'KB001').
            quantity: Quantity of units to purchase (must be >= 1, defaults to 1).

        Returns:
            Dictionary containing policy decision verdict ('APPROVED' or 'REJECTED'),
            reasoning, transaction ID, computed amount, mandate limit, and payment outcome.
        """
        return propose_purchase_handler(
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
        )

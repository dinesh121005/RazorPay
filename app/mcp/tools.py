"""
MCP tool definitions and handlers for ai-buyer-gateway.

Exposes tools to AI clients (e.g. Claude Desktop) over both:
1. Local stdio transport (single-user demo mode with inquire_merchant + search_products + propose_purchase)
2. Remote Streamable HTTP transport (OAuth-authenticated multi-tenant mode with propose_purchase bound to verified JWT sub)

Data Minimization:
MCP tools return minimized, customer-facing response shapes. Internal transaction UUIDs,
Razorpay order IDs, and payment rails internals are intentionally withheld from AI clients
and preserved exclusively in the SQLite audit trail for admin inspection.
"""
from contextvars import ContextVar
from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer

from app.agent.service import (
    PurchaseResponse,
    execute_purchase,
    generate_bucketed_idempotency_key,
)
from app.catalog.service import get_product, search_products
from app.exceptions import GatewayError
from app.merchant_agent.models import InquiryRequest
from app.merchant_agent.service import merchant_agent_service
from app.policy.store import mandate_store

# Context variable holding the verified customer_id from validated OAuth JWT on remote HTTP requests
authenticated_customer_id: ContextVar[Optional[str]] = ContextVar("authenticated_customer_id", default=None)


def to_customer_response(full_response: PurchaseResponse) -> Dict[str, Any]:
    """
    Projects the full internal PurchaseResponse into a minimized customer-facing payload.

    Data Confidentiality Safeguard:
    Raw transaction UUIDs (transaction_id) and payment gateway identifiers (razorpay_order_id)
    are strictly omitted from AI/customer-facing MCP responses to prevent unintentional data leakage.
    Full traceability is preserved internally and remains queryable via admin /audit endpoints.
    """
    product = get_product(full_response.product_id)
    ref_code = (
        f"REF-{full_response.transaction_id[-8:].upper()}"
        if full_response.decision == "APPROVED"
        else None
    )

    return {
        "decision": full_response.decision,
        "product_name": product.name,
        "amount": full_response.amount,
        "reason": full_response.reason,
        "reference_code": ref_code,
    }


def inquire_merchant_handler(
    query: str,
    max_budget: Optional[float] = None,
    category: Optional[str] = None,
    quantity: int = 1,
) -> Dict[str, Any]:
    """
    Handler allowing Buyer AI Agents (Claude) to consult the Merchant Sales Agent
    with natural language queries and obtain smart product quotes and recommendations.
    """
    req = InquiryRequest(
        query=query,
        max_budget=max_budget,
        category=category,
        quantity=quantity,
    )
    res = merchant_agent_service.process_inquiry(req)
    return res.model_dump()


def search_products_handler(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Handler executing product search against the catalog service.
    Returns list of matching product dicts with customer-facing fields (id, name, category, price).
    """
    products = search_products(query=query, category=category, max_price=max_price)
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": p.price,
        }
        for p in products
    ]


def resolve_customer_handler(identifier: str) -> Dict[str, Any]:
    """
    Handler resolving a customer's human-identifiable name, email, or identifier to their customer_id.
    - Unambiguous single match: returns {"resolved": True, "customer_id": "<id>", "display_name": "<name>"}
    - Zero matches: returns {"resolved": False, "reason": "no_match", "message": "<friendly message>"}
    - Multiple matches: returns {"resolved": False, "reason": "ambiguous", "candidates": [...], "message": "<clarify message>"}
    """
    if not identifier or not str(identifier).strip():
        return {
            "resolved": False,
            "reason": "no_match",
            "message": "Identifier cannot be empty.",
        }

    matches = mandate_store.find_by_identifier(identifier)

    if len(matches) == 1:
        match = matches[0]
        return {
            "resolved": True,
            "customer_id": match.customer_id,
            "display_name": match.display_name,
        }
    elif len(matches) == 0:
        return {
            "resolved": False,
            "reason": "no_match",
            "message": f"No authorized customer found matching '{identifier}'.",
        }
    else:
        return {
            "resolved": False,
            "reason": "ambiguous",
            "candidates": [m.display_name for m in matches],
            "message": f"Multiple customers found matching '{identifier}'. Please ask the user to clarify with their exact full name or email.",
        }


def propose_purchase_handler(
    customer_id: Optional[str] = None,
    product_id: str = "",
    quantity: int = 1,
) -> Dict[str, Any]:
    """
    Core handler executing a purchase proposal through the gateway for local stdio mode.
    Defaults to CUST001 (Dinesh Kumar) if no customer_id is specified.
    Returns data-minimized customer-facing dict.
    Catches domain errors and converts them to structured rejected responses for the agent.
    """
    effective_customer_id = (customer_id or "CUST001").strip()
    try:
        idempotency_key = generate_bucketed_idempotency_key(effective_customer_id, product_id, quantity)
        response = execute_purchase(
            customer_id=effective_customer_id,
            product_id=product_id,
            quantity=quantity,
            idempotency_key=idempotency_key,
        )
        return to_customer_response(response)
    except GatewayError as e:
        return {
            "decision": "REJECTED",
            "product_name": product_id,
            "amount": 0.0,
            "reason": str(e),
            "reference_code": None,
        }
    except Exception as e:
        import logging
        logging.getLogger("gateway.mcp").error("Error executing purchase proposal: %s", e, exc_info=True)
        return {
            "decision": "REJECTED",
            "product_name": product_id,
            "amount": 0.0,
            "reason": f"System error during purchase processing: {str(e)}",
            "reference_code": None,
        }


def propose_purchase_remote_handler(
    product_id: str,
    quantity: int = 1,
) -> Dict[str, Any]:
    """
    Core handler executing a purchase proposal for the remote OAuth-authenticated MCP path.
    Identity is bound strictly to the validated JWT sub claim (authenticated_customer_id).
    Caller-supplied customer_id parameter is intentionally omitted and impossible to override.
    """
    customer_id = authenticated_customer_id.get()
    if not customer_id:
        return {
            "decision": "REJECTED",
            "product_name": product_id,
            "amount": 0.0,
            "reason": "Unauthenticated tool call: missing or unverified customer identity.",
            "reference_code": None,
        }

    return propose_purchase_handler(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
    )


def register_tools(server: MCPServer) -> None:
    """
    Registers local stdio gateway tools with the MCP server instance.
    Includes inquire_merchant, search_products, resolve_customer, and propose_purchase.
    """
    @server.tool(
        name="inquire_merchant",
        description=(
            "Consult the Merchant Sales AI Agent with a natural language procurement inquiry "
            "(e.g. 'i want keyboard', 'buy keyboard', 'clicky keyboard for coding', '4k monitor under 5000'). "
            "CRITICAL: Call this tool IMMEDIATELY on ANY user message mentioning wanting, needing, looking for, or purchasing ANY item "
            "(e.g. 'i want keyboard', 'i need a monitor', 'buy snacks'). "
            "Never do a web search or ask conversational questions first — ALWAYS call inquire_merchant to get quotes from the store's Merchant Agent first."
        )
    )
    def inquire_merchant_tool(
        query: str,
        max_budget: Optional[float] = None,
        category: Optional[str] = None,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Consult the Merchant Sales Agent for quotes and recommendations."""
        return inquire_merchant_handler(
            query=query,
            max_budget=max_budget,
            category=category,
            quantity=quantity,
        )

    @server.tool(
        name="search_products",
        description=(
            "Search catalog products by name, category, or maximum price. "
            "Call this before propose_purchase whenever you don't already have an exact product ID. "
            "Never ask the customer for a product ID directly — search for it. "
            "CRITICAL: Call this tool IMMEDIATELY whenever the user mentions wanting to buy, find, check, order, or purchase ANY item "
            "(e.g. 'buy the keyboard', 'buy keyboard', 'get a monitor', 'find food'), even if the user didn't specify a brand, price, or full details."
        )
    )
    def search_products_tool(
        query: Optional[str] = None,
        category: Optional[str] = None,
        max_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search catalog products.

        Args:
            query: Optional search keyword to match against product names (case-insensitive substring).
            category: Optional category to filter products by (case-insensitive exact match).
            max_price: Optional maximum price threshold in INR (₹).

        Returns:
            List of matching products with their IDs, names, categories, and prices.
        """
        return search_products_handler(
            query=query,
            category=category,
            max_price=max_price,
        )

    @server.tool(
        name="resolve_customer",
        description=(
            "Resolve a customer's display name or email to their authorized customer_id. "
            "Only use this if switching to a specific secondary customer account. "
            "Do NOT ask the user for their name or email during standard shopping, as the local user is already authenticated as CUST001."
        )
    )
    def resolve_customer(
        identifier: str,
    ) -> Dict[str, Any]:
        """
        Resolve a human identity to a customer_id.

        Args:
            identifier: Human name (e.g. 'Dinesh Kumar', 'Dinesh', 'Alex') or email address.

        Returns:
            Dictionary with resolution status ('resolved': True/False) and resolved 'customer_id'.
        """
        return resolve_customer_handler(identifier=identifier)

    @server.tool(
        name="propose_purchase",
        description=(
            "Propose an agent purchase transaction under customer mandate rules. "
            "The gateway evaluates deterministic policy rules (budget limit, merchant, "
            "category, expiration) and creates a Razorpay Test Mode order ONLY if approved. "
            "IMPORTANT: The local customer account is already authenticated as CUST001 (Dinesh Kumar). "
            "NEVER ask the user for their name, email, or customer ID — call propose_purchase immediately. "
            "An agent may only propose, never authorize. "
            "This only proposes a purchase for policy evaluation — it does not guarantee approval. "
            "The Policy Engine independently verifies the mandate."
        )
    )
    def propose_purchase(
        product_id: str,
        quantity: int = 1,
        customer_id: str = "CUST001",
    ) -> Dict[str, Any]:
        """
        Propose a purchase on behalf of a customer.

        Args:
            product_id: Product ID from the catalog to purchase (e.g. 'KB001').
            quantity: Quantity of units to purchase (must be >= 1, defaults to 1).
            customer_id: Unique customer identifier (defaults automatically to 'CUST001').

        Returns:
            Minimized dictionary containing policy decision verdict ('APPROVED' or 'REJECTED'),
            product name, total amount, plain-language reason, and human-friendly reference code.
        """
        return propose_purchase_handler(
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
        )


def register_remote_tools(server: MCPServer) -> None:
    """
    Registers remote OAuth-authenticated gateway tools with the remote MCP server instance.
    `propose_purchase` accepts ONLY product_id and quantity — customer identity is extracted
    exclusively from the verified OAuth JWT sub claim.
    """
    @server.tool(
        name="inquire_merchant",
        description=(
            "Consult the Merchant Sales AI Agent with a natural language procurement inquiry "
            "(e.g. 'i want keyboard', 'buy keyboard', 'clicky keyboard for coding', '4k monitor under 5000'). "
            "CRITICAL: Call this tool IMMEDIATELY on ANY user message mentioning wanting, needing, looking for, or purchasing ANY item. "
            "Never do a web search or ask conversational questions first — ALWAYS call inquire_merchant to get quotes from the store's Merchant Agent first."
        )
    )
    def inquire_merchant_tool(
        query: str,
        max_budget: Optional[float] = None,
        category: Optional[str] = None,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Consult the Merchant Sales Agent for quotes and recommendations."""
        return inquire_merchant_handler(
            query=query,
            max_budget=max_budget,
            category=category,
            quantity=quantity,
        )

    @server.tool(
        name="search_products",
        description=(
            "Search catalog products by name, category, or maximum price. "
            "Call this before propose_purchase whenever you don't already have an exact product ID. "
            "Never ask the customer for a product ID directly — search for it."
        )
    )
    def search_products_tool(
        query: Optional[str] = None,
        category: Optional[str] = None,
        max_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search catalog products."""
        return search_products_handler(
            query=query,
            category=category,
            max_price=max_price,
        )

    @server.tool(
        name="propose_purchase",
        description=(
            "Propose a purchase transaction on behalf of the authenticated customer. "
            "Customer identity is automatically bound from the verified OAuth session. "
            "The gateway evaluates deterministic policy rules (budget limit, merchant, "
            "category, expiration) and creates a Razorpay Test Mode order ONLY if approved. "
            "CRITICAL: When the user asks you to buy, get, or order an item, call this tool IMMEDIATELY "
            "in the same turn after getting the product quote from inquire_merchant without asking for extra human confirmation."
        )
    )
    def propose_purchase_remote(
        product_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Propose a purchase on behalf of the authenticated customer.

        Args:
            product_id: Product ID from the catalog to purchase (e.g. 'KB001').
            quantity: Quantity of units to purchase (must be >= 1, defaults to 1).

        Returns:
            Minimized dictionary containing policy decision verdict ('APPROVED' or 'REJECTED'),
            product name, total amount, plain-language reason, and human-friendly reference code.
        """
        return propose_purchase_remote_handler(
            product_id=product_id,
            quantity=quantity,
        )

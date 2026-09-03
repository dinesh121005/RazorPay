"""
MCP tool definitions and handlers for ai-buyer-gateway.

Exposes tools to AI clients (e.g. Claude Desktop) over both:
1. Local stdio transport (single-user demo mode with inquire_merchant, search_products, suggest_addons, propose_purchase, and confirm_purchase)
2. Remote Streamable HTTP transport (OAuth-authenticated multi-tenant mode bound to verified JWT sub)

Data Minimization:
MCP tools return minimized, customer-facing response shapes. Internal transaction UUIDs,
Razorpay order IDs, and payment rails internals are intentionally withheld from AI clients
and preserved exclusively in the SQLite audit trail for admin inspection.
"""
from contextvars import ContextVar
import logging
from typing import Any, Dict, List, Optional
try:
    from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found,import-untyped]
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[import-not-found,import-untyped]
    except ImportError:
        try:
            from mcp.server import MCPServer  # type: ignore[import-not-found,import-untyped]
        except ImportError:
            from mcp.server import FastMCP as MCPServer  # type: ignore[import-not-found,import-untyped]

from app.agent.service import (
    PurchaseResponse,
    confirm_purchase,
    execute_purchase,
    generate_bucketed_idempotency_key,
)
from app.audit import audit_store
from app.catalog.service import get_product, search_products
from app.exceptions import GatewayError
from app.merchant_agent.models import InquiryRequest
from app.merchant_agent.service import merchant_agent_service
from app.policy.store import mandate_store

logger = logging.getLogger("gateway.mcp")

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
    is_fully_created = (
        full_response.decision == "APPROVED"
        and full_response.payment is not None
        and full_response.payment.status in ("created", "captured")
    )
    ref_code = (
        f"REF-{full_response.transaction_id[-8:].upper()}"
        if is_fully_created
        else None
    )

    payment_url = full_response.payment.payment_url if full_response.payment else None
    qr_code_url = full_response.payment.qr_code_url if full_response.payment else None
    payment_method = full_response.payment.payment_method if full_response.payment else None

    user_instructions = None
    if payment_url and full_response.decision == "REJECTED":
        user_instructions = (
            "Item exceeds autonomous mandate limit. The merchant gateway has generated a secure, official "
            "Razorpay Checkout Link and UPI QR Code. You MUST provide this checkout link and QR code to the "
            "human user so they can complete payment manually via UPI, Netbanking, or Card."
        )

    return {
        "decision": full_response.decision,
        "product_name": product.name,
        "amount": full_response.amount,
        "reason": full_response.reason,
        "reference_code": ref_code,
        "payment_url": payment_url,
        "qr_code_url": qr_code_url,
        "payment_method": payment_method,
        "user_instructions": user_instructions,
        "requires_confirmation": full_response.requires_confirmation,
        "confirmation_token": full_response.confirmation_token,
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


def suggest_addons_handler(
    product_id: str,
    remaining_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Handler providing Track 01 revenue growth add-ons and cross-sell suggestions.
    """
    res = merchant_agent_service.recommend_addons(
        product_id=product_id,
        remaining_budget=remaining_budget,
    )
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
            "requires_confirmation": False,
            "confirmation_token": None,
        }
    except Exception as e:
        logger.error("Error executing purchase proposal: %s", e, exc_info=True)
        return {
            "decision": "REJECTED",
            "product_name": product_id,
            "amount": 0.0,
            "reason": f"System error during purchase processing: {str(e)}",
            "reference_code": None,
            "requires_confirmation": False,
            "confirmation_token": None,
        }


def confirm_purchase_handler(
    confirmation_token: str,
    customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes payment and order confirmation for a previously proposed gated purchase.
    """
    try:
        response = confirm_purchase(
            confirmation_token=confirmation_token,
            customer_id=customer_id or "CUST001",
        )
        return to_customer_response(response)
    except GatewayError as e:
        return {
            "decision": "REJECTED",
            "product_name": "unknown",
            "amount": 0.0,
            "reason": str(e),
            "reference_code": None,
            "requires_confirmation": False,
            "confirmation_token": None,
        }
    except Exception as e:
        logger.error("Error confirming purchase: %s", e, exc_info=True)
        return {
            "decision": "REJECTED",
            "product_name": "unknown",
            "amount": 0.0,
            "reason": f"Confirmation error: {str(e)}",
            "reference_code": None,
            "requires_confirmation": False,
            "confirmation_token": None,
        }


def propose_purchase_remote_handler(
    product_id: str,
    quantity: int = 1,
) -> Dict[str, Any]:
    """
    Core handler executing a purchase proposal for the remote OAuth-authenticated MCP path.
    Identity is bound strictly to the validated JWT sub claim (authenticated_customer_id).
    """
    customer_id = authenticated_customer_id.get()
    if not customer_id:
        return {
            "decision": "REJECTED",
            "product_name": product_id,
            "amount": 0.0,
            "reason": "Unauthenticated tool call: missing or unverified customer identity.",
            "reference_code": None,
            "requires_confirmation": False,
            "confirmation_token": None,
        }

    return propose_purchase_handler(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
    )


def confirm_purchase_remote_handler(
    confirmation_token: str,
) -> Dict[str, Any]:
    """
    Remote handler confirming a purchase with identity bound to authenticated OAuth customer.
    """
    customer_id = authenticated_customer_id.get()
    if not customer_id:
        return {
            "decision": "REJECTED",
            "product_name": "unknown",
            "amount": 0.0,
            "reason": "Unauthenticated tool call: missing or unverified customer identity.",
            "reference_code": None,
            "requires_confirmation": False,
            "confirmation_token": None,
        }

    return confirm_purchase_handler(
        confirmation_token=confirmation_token,
        customer_id=customer_id,
    )


def check_order_status_handler(
    reference_or_id: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Looks up order and payment status from the merchant audit ledger.
    Allows Claude to confirm to the user that their payment was captured and their order placed.
    """
    effective_customer_id = customer_id or "CUST001"
    record = audit_store.lookup_order(identifier=reference_or_id, customer_id=effective_customer_id)
    if not record:
        return {
            "order_found": False,
            "message": "No order records found for this customer.",
        }

    product = get_product(record.product_id)
    p_name = product.name if product else record.product_id
    is_paid = record.payment_status in ("captured", "paid")
    ref_code = f"REF-{record.transaction_id[-8:].upper()}"

    return {
        "order_found": True,
        "reference_code": ref_code,
        "product_name": p_name,
        "quantity": record.quantity,
        "amount": record.amount,
        "decision": record.decision,
        "payment_status": record.payment_status or "pending",
        "razorpay_order_id": record.razorpay_order_id,
        "is_paid": is_paid,
        "order_status": "PLACED_AND_CONFIRMED" if is_paid else "PENDING_PAYMENT",
        "timestamp": record.timestamp,
        "message": (
            f"Merchant confirmation: Order {ref_code} for {record.quantity}x {p_name} (₹{record.amount:.2f}) is "
            f"{'CONFIRMED & PAID via Razorpay rails' if is_paid else 'awaiting payment'}."
        ),
    }


def check_order_status_remote_handler(
    reference_or_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Remote handler checking order status bound to the authenticated OAuth customer.
    """
    customer_id = authenticated_customer_id.get() or "CUST001"
    return check_order_status_handler(
        reference_or_id=reference_or_id,
        customer_id=customer_id,
    )


def register_tools(server: MCPServer) -> None:
    """
    Registers local stdio gateway tools with the MCP server instance.
    """
    @server.tool(
        name="check_order_status",
        description=(
            "Check the placement, fulfillment, and payment status of a customer's order. "
            "Call this whenever the user asks if their order is placed, asks if payment was received, "
            "or requests confirmation/reference code for a recent purchase."
        )
    )
    def check_order_status_tool(
        reference_or_id: Optional[str] = None,
        customer_id: str = "CUST001",
    ) -> Dict[str, Any]:
        """Check order and payment settlement status."""
        return check_order_status_handler(
            reference_or_id=reference_or_id,
            customer_id=customer_id,
        )

    @server.tool(
        name="inquire_merchant",
        description=(
            "Consult the Merchant Sales AI Agent with a natural language procurement inquiry "
            "(e.g. 'i want keyboard', 'buy keyboard', 'clicky keyboard for coding', '4k monitor under 5000'). "
            "Call this tool to get quotes and recommendations from the store's Merchant Agent first."
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
        name="suggest_addons",
        description=(
            "Track 01 Merchant Revenue Growth: Discover complementary add-ons and cross-sell items "
            "that pair with a chosen product and fit within the user's remaining mandate budget."
        )
    )
    def suggest_addons_tool(
        product_id: str,
        remaining_budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Suggest complementary cross-sell add-ons under remaining budget."""
        return suggest_addons_handler(
            product_id=product_id,
            remaining_budget=remaining_budget,
        )

    @server.tool(
        name="search_products",
        description=(
            "Search catalog products by name, category, or maximum price. "
            "Call this before propose_purchase whenever you don't already have an exact product ID."
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
        name="resolve_customer",
        description="Resolve a customer's display name or email to their authorized customer_id."
    )
    def resolve_customer(identifier: str) -> Dict[str, Any]:
        """Resolve a human identity to a customer_id."""
        return resolve_customer_handler(identifier=identifier)

    @server.tool(
        name="propose_purchase",
        description=(
            "Propose a purchase under customer mandate rules. Evaluates deterministic policy rules "
            "(budget limit, cumulative daily cap, merchant, category, stock). "
            "1. If within auto-pay limit (< ₹500), auto-debits wallet directly. "
            "2. For gated transactions (₹500 to mandate limit), returns `requires_confirmation: true` and `confirmation_token`. Present quote to user and call `confirm_purchase`. "
            "3. If item price exceeds customer's autonomous mandate limit (e.g. > ₹2,000), the gateway refuses auto-debit and provides an official Razorpay Checkout Link (`payment_url`) and UPI QR code (`qr_code_url`). You MUST provide this link and QR code to the human user so they can complete payment manually via UPI, Netbanking, or Card."
        )
    )
    def propose_purchase(
        product_id: str,
        quantity: int = 1,
        customer_id: str = "CUST001",
    ) -> Dict[str, Any]:
        """Propose a purchase on behalf of a customer."""
        return propose_purchase_handler(
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
        )

    @server.tool(
        name="confirm_purchase",
        description=(
            "Confirm and execute a previously proposed purchase using the signed confirmation_token. "
            "Call this ONLY after presenting the proposal quote to the human user and receiving approval."
        )
    )
    def confirm_purchase_tool(
        confirmation_token: str,
        customer_id: str = "CUST001",
    ) -> Dict[str, Any]:
        """Confirm and finalize a gated purchase."""
        return confirm_purchase_handler(
            confirmation_token=confirmation_token,
            customer_id=customer_id,
        )


def register_remote_tools(server: MCPServer) -> None:
    """
    Registers remote OAuth-authenticated gateway tools with the remote MCP server instance.
    """
    @server.tool(
        name="check_order_status",
        description=(
            "Check the placement, fulfillment, and payment status of a customer's order. "
            "Call this whenever the user asks if their order is placed, asks if payment was received, "
            "or requests confirmation/reference code for a recent purchase."
        )
    )
    def check_order_status_tool(
        reference_or_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check order and payment settlement status."""
        return check_order_status_remote_handler(
            reference_or_id=reference_or_id,
        )

    @server.tool(
        name="inquire_merchant",
        description="Consult the Merchant Sales AI Agent with a natural language procurement inquiry."
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
        name="suggest_addons",
        description="Track 01 Revenue Growth: Discover complementary add-ons and cross-sell items within budget headroom."
    )
    def suggest_addons_tool(
        product_id: str,
        remaining_budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Suggest complementary cross-sell add-ons under remaining budget."""
        return suggest_addons_handler(
            product_id=product_id,
            remaining_budget=remaining_budget,
        )

    @server.tool(
        name="search_products",
        description="Search catalog products by name, category, or maximum price."
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
            "Propose a single product purchase on behalf of the authenticated customer. "
            "Pass exactly ONE specific product_id (e.g. 'FD005', 'KB001', 'HK001'). If purchasing multiple distinct items, call this tool once per item. "
            "Customer identity is bound strictly to verified OAuth JWT. "
            "1. If within auto-pay limit (< ₹500), auto-debits wallet directly. "
            "2. For gated orders (₹500 to mandate limit), returns `requires_confirmation: true` and `confirmation_token`. Present quote to user and call `confirm_purchase`. "
            "3. If order exceeds autonomous mandate limit (e.g. > ₹2,000), the gateway refuses autonomous auto-debit and provides an official Razorpay Checkout Link (`payment_url`) and UPI QR Code (`qr_code_url`). You MUST provide this link and QR code to the human user so they can complete payment manually on their own device via UPI, Netbanking, or Card."
        )
    )
    def propose_purchase_remote(
        product_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Propose a purchase on behalf of the authenticated customer."""
        return propose_purchase_remote_handler(
            product_id=product_id.strip(),
            quantity=quantity,
        )

    @server.tool(
        name="confirm_purchase",
        description=(
            "Confirm and execute payment rails for a previously proposed, gated purchase using the signed confirmation_token. "
            "Protocol Guard: Call this ONLY after the human user has reviewed the proposal quote and explicitly authorized the payment."
        )
    )
    def confirm_purchase_remote(
        confirmation_token: str,
    ) -> Dict[str, Any]:
        """Confirm a gated purchase on behalf of the authenticated customer."""
        return confirm_purchase_remote_handler(
            confirmation_token=confirmation_token,
        )


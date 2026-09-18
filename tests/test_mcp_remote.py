"""
Tests for Remote Streamable HTTP MCP Server & OAuth Bearer Token Verification.
"""
import datetime
import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp.server import create_remote_mcp_server
from app.mcp.tools import (
    authenticated_customer_id,
    propose_purchase_remote_handler,
)
from app.oauth.crypto import create_access_token

client = TestClient(app)

_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_RemoteMCP_12345",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "remote-receipt-123",
}


def test_remote_mcp_unauthenticated_rejected_401():
    """Requests to /mcp without Authorization header are rejected with 401 and WWW-Authenticate header."""
    response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert "Missing or malformed Bearer token" in data["error"]["message"]
    # Verify WWW-Authenticate discovery metadata headers
    assert "www-authenticate" in response.headers
    assert 'resource_metadata="/.well-known/oauth-protected-resource"' in response.headers["www-authenticate"]
    assert 'as_uri="/.well-known/oauth-authorization-server"' in response.headers["www-authenticate"]


def test_remote_mcp_invalid_token_rejected_401():
    """Requests to /mcp with an invalid token signature are rejected with 401 and WWW-Authenticate."""
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
    assert response.status_code == 401
    assert "Invalid access token" in response.json()["error"]["message"]
    assert "www-authenticate" in response.headers
    assert "invalid_token" in response.headers["www-authenticate"]


def test_remote_mcp_expired_token_rejected_401():
    """Requests to /mcp with an expired token are rejected with 401."""
    expired_token = create_access_token(
        customer_id="CUST001",
        expires_delta=datetime.timedelta(seconds=-10),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
    assert response.status_code == 401
    assert "Access token has expired" in response.json()["error"]["message"]


def test_remote_mcp_tool_schema_omits_customer_id():
    """
    Remote MCP server schema must NOT require or accept customer_id in propose_purchase.
    Identity is bound exclusively from the validated OAuth session.
    """
    remote_server = create_remote_mcp_server()
    pytest.importorskip("anyio")

    async def _check_tools():
        tools = await remote_server.list_tools()
        tool_names = [t.name for t in tools]
        assert "inquire_merchant" in tool_names
        assert "search_products" in tool_names
        assert "suggest_addons" in tool_names
        assert "propose_purchase" in tool_names
        assert "confirm_purchase" in tool_names
        # resolve_customer is not needed on remote path
        assert "resolve_customer" not in tool_names

        propose_tool = next(t for t in tools if t.name == "propose_purchase")
        schema = getattr(propose_tool, "input_schema", getattr(propose_tool, "inputSchema", {}))
        # customer_id must NOT be in the schema properties
        assert "customer_id" not in schema.get("properties", {})
        assert "product_id" in schema.get("properties", {})
        assert "quantity" in schema.get("properties", {})

    import anyio
    anyio.run(_check_tools)


def test_remote_mcp_propose_and_confirm_purchase_authenticated_flow():
    """
    When authenticated as CUST001 via OAuth context, propose_purchase_remote_handler
    evaluates mandate and returns confirmation token for gated purchase (>= ₹500).
    confirm_purchase_remote_handler then finalizes order.
    """
    from app.mcp.tools import confirm_purchase_remote_handler

    token_reset = authenticated_customer_id.set("CUST001")
    try:
        # Step 1: Propose (Gated)
        with patch(_CREATE_ORDER) as mock_create_1:
            prop_result = propose_purchase_remote_handler(
                product_id="KB001",
                quantity=1,
            )
        mock_create_1.assert_not_called()
        assert prop_result["decision"] == "PENDING_CONFIRMATION"
        assert prop_result["requires_confirmation"] is True
        assert prop_result["confirmation_token"] is not None

        # Step 2: Confirm
        with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create_2:
            conf_result = confirm_purchase_remote_handler(
                confirmation_token=prop_result["confirmation_token"],
            )

        mock_create_2.assert_called_once()
        assert conf_result["decision"] == "APPROVED"
        assert conf_result["product_name"] == "Mechanical Gaming Keyboard"
        assert conf_result["amount"] == 1499.0
        assert conf_result["reference_code"].startswith("REF-")
        # Assert data minimization
        assert "transaction_id" not in conf_result
        assert "razorpay_order_id" not in conf_result
    finally:
        authenticated_customer_id.reset(token_reset)


def test_remote_mcp_propose_purchase_unauthenticated_rejection():
    """
    If no customer is authenticated in context, propose_purchase_remote_handler returns
    structured rejection rather than crashing.
    """
    token_reset = authenticated_customer_id.set(None)
    try:
        result = propose_purchase_remote_handler(
            product_id="KB001",
            quantity=1,
        )
        assert result["decision"] == "REJECTED"
        assert "Unauthenticated" in result["reason"]
    finally:
        authenticated_customer_id.reset(token_reset)



def test_remote_mcp_impersonation_immunity():
    """
    Even if a malicious caller or prompt tries to execute an action for CUST002,
    the authenticated JWT sub (CUST001) dictates the policy evaluation.
    CUST001 has budget ₹2,000; CUST002 has budget ₹1,500 and MERCH_FOOD disallowed.
    """
    # Authenticated as CUST001 (allowed MERCH_FOOD)
    token_reset = authenticated_customer_id.set("CUST001")
    try:
        with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
            # FD001 is from MERCH_FOOD (allowed for CUST001, disallowed for CUST002)
            result = propose_purchase_remote_handler(
                product_id="FD001",
                quantity=1,
            )
        mock_create.assert_called_once()
        # Evaluated under CUST001 -> APPROVED
        assert result["decision"] == "APPROVED"
    finally:
        authenticated_customer_id.reset(token_reset)

    # Authenticated as CUST002 (disallowed MERCH_FOOD)
    token_reset2 = authenticated_customer_id.set("CUST002")
    try:
        with patch(_CREATE_ORDER) as mock_create_none:
            result = propose_purchase_remote_handler(
                product_id="FD001",
                quantity=1,
            )
        mock_create_none.assert_not_called()
        # Evaluated under CUST002 -> REJECTED
        assert result["decision"] == "REJECTED"
        assert "MERCH_FOOD" in result["reason"]
    finally:
        authenticated_customer_id.reset(token_reset2)


def test_razorpay_token_isolation():
    """
    Verifies that customer OAuth access tokens are NEVER forwarded or leaked to Razorpay.
    Razorpay SDK calls must only receive merchant credentials and standard transaction notes.
    """
    raw_token = create_access_token(customer_id="CUST001")
    token_reset = authenticated_customer_id.set("CUST001")
    try:
        with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
            propose_purchase_remote_handler(
                product_id="FD001",
                quantity=1,
            )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs if mock_create.call_args.kwargs else mock_create.call_args[1]
        if not call_kwargs and mock_create.call_args.args:
            call_kwargs = mock_create.call_args.args[0]

        # Convert all call arguments to string and ensure raw_token is not present anywhere
        serialized_args = json.dumps(call_kwargs, default=str)
        assert raw_token not in serialized_args
        assert "Bearer" not in serialized_args
    finally:
        authenticated_customer_id.reset(token_reset)


def test_remote_mcp_search_products_integration():
    """
    Integration test: remote search_products handler returns product records matching query.
    """
    from app.mcp.tools import search_products_handler

    # 1. Search keyboard
    kb_res = search_products_handler(query="keyboard")
    assert len(kb_res) >= 1
    assert any(p["id"] == "KB001" for p in kb_res)

    # 2. Search webcam
    wc_res = search_products_handler(query="webcam")
    assert len(wc_res) >= 1
    assert any(p["id"] == "EL004" for p in wc_res)

    # 3. Search mouse
    m_res = search_products_handler(query="mouse")
    assert len(m_res) >= 1
    assert any(p["id"] == "EL001" for p in m_res)

    # 4. FastMCP call_tool async test
    remote_server = create_remote_mcp_server()

    async def _check_mcp_call():
        res = await remote_server.call_tool("search_products", {"query": "webcam"})
        assert res.is_error is False
        assert len(res.structured_content["result"]) >= 1
        assert any(p["id"] == "EL004" for p in res.structured_content["result"])

    import anyio
    anyio.run(_check_mcp_call)


def test_mcp_rest_catalog_alignment():
    """
    Verifies that the product set returned via REST GET /products matches the MCP catalog search products.
    Detects any accidental divergence between REST catalog and MCP catalog.
    """
    from app.mcp.tools import search_products_handler

    rest_res = client.get("/products")
    assert rest_res.status_code == 200
    rest_products = rest_res.json()
    rest_ids = {p["id"] for p in rest_products}

    mcp_products = search_products_handler()
    mcp_ids = {p["id"] for p in mcp_products}

    assert rest_ids == mcp_ids, f"Catalog divergence detected! REST has {len(rest_ids)} products, MCP has {len(mcp_ids)} products."



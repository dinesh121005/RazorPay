"""
Tests for Phase 4 — Model Context Protocol (MCP) Wrapper.

Verifies:
1. Tool handler unit tests (propose_purchase_handler parity with HTTP router).
2. Canonical approved (KB001) and rejected (MN001) flows.
3. Multi-merchant cross-merchant approval (FD001) and rejection (CUST002).
4. Error handling (unknown product, unknown customer raising 404).
5. MCP Server tool listing and schema inspection.
6. Async MCP protocol tool execution via server.call_tool.
"""
import json
from unittest.mock import patch
import pytest
from fastapi import HTTPException

from app.audit import audit_store
from app.mcp.server import (
    create_mcp_server,
    mcp_server,
)
from app.mcp.tools import (
    propose_purchase_handler,
)

_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_MCPTest_ABC123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "some-mcp-txn-id",
}


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """
    Ensure all MCP tests execute against an isolated SQLite test database.
    """
    test_db = str(tmp_path / "test_mcp_gateway.db")
    monkeypatch.setattr(audit_store, "db_path", test_db)
    audit_store._init_db()
    yield test_db


# ══════════════════════════════════════════════════════════════════════════════
# 1. MCP Tool Handler Unit Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_mcp_tool_approved_canonical():
    """
    CUST001 + KB001 (₹1,499 <= ₹2,000) -> APPROVED.
    Asserts Razorpay order creation and full response shape parity with HTTP router.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        result = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    mock_create.assert_called_once()
    assert result["decision"] == "APPROVED"
    assert result["product_id"] == "KB001"
    assert result["amount"] == 1499.0
    assert result["mandate_limit"] == 2000.0
    assert "within mandate limit" in result["reason"]
    assert result["transaction_id"] is not None
    assert len(result["transaction_id"]) == 36

    # Payment output
    assert result["payment"] is not None
    assert result["payment"]["status"] == "created"
    assert result["payment"]["razorpay_order_id"] == "order_MCPTest_ABC123"
    assert result["payment"]["error"] is None


def test_mcp_tool_rejected_over_limit_canonical():
    """
    CUST001 + MN001 (₹4,999 > ₹2,000) -> REJECTED.
    Asserts payment is None and Razorpay is never invoked.
    """
    with patch(_CREATE_ORDER) as mock_create:
        result = propose_purchase_handler(
            customer_id="CUST001",
            product_id="MN001",
            quantity=1,
        )

    mock_create.assert_not_called()
    assert result["decision"] == "REJECTED"
    assert result["product_id"] == "MN001"
    assert result["amount"] == 4999.0
    assert result["mandate_limit"] == 2000.0
    assert "exceeds maximum mandate limit" in result["reason"]
    assert result["payment"] is None


def test_mcp_tool_cross_merchant_food_approved():
    """
    CUST001 + FD001 (MERCH_FOOD, ₹349 <= ₹2,000) -> APPROVED.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        result = propose_purchase_handler(
            customer_id="CUST001",
            product_id="FD001",
            quantity=1,
        )

    assert result["decision"] == "APPROVED"
    assert result["amount"] == 349.0
    assert result["payment"]["status"] == "created"


def test_mcp_tool_merchant_rejection_cust002():
    """
    CUST002 + FD001 (MERCH_FOOD disallowed for CUST002) -> REJECTED (MERCHANT_NOT_ALLOWED).
    """
    with patch(_CREATE_ORDER) as mock_create:
        result = propose_purchase_handler(
            customer_id="CUST002",
            product_id="FD001",
            quantity=1,
        )

    mock_create.assert_not_called()
    assert result["decision"] == "REJECTED"
    assert "MERCH_FOOD" in result["reason"]
    assert result["payment"] is None


def test_mcp_tool_unknown_product_raises_404():
    """
    Unknown product ID raises HTTPException 404.
    """
    with pytest.raises(HTTPException) as exc_info:
        propose_purchase_handler(
            customer_id="CUST001",
            product_id="NON_EXISTENT_PROD",
            quantity=1,
        )
    assert exc_info.value.status_code == 404
    assert "NON_EXISTENT_PROD" in exc_info.value.detail


def test_mcp_tool_unknown_customer_raises_404():
    """
    Unknown customer ID raises HTTPException 404.
    """
    with pytest.raises(HTTPException) as exc_info:
        propose_purchase_handler(
            customer_id="NON_EXISTENT_CUST",
            product_id="KB001",
            quantity=1,
        )
    assert exc_info.value.status_code == 404
    assert "NON_EXISTENT_CUST" in exc_info.value.detail


# ══════════════════════════════════════════════════════════════════════════════
# 2. MCP Server Protocol Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_mcp_server_lists_propose_purchase_tool():
    """
    Inspects tools exposed by the MCP server and verifies propose_purchase schema.
    """
    server = create_mcp_server()
    tools = await server.list_tools()

    tool_names = [t.name for t in tools]
    assert "propose_purchase" in tool_names

    tool = next(t for t in tools if t.name == "propose_purchase")
    schema = getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))
    assert "customer_id" in schema["properties"]
    assert "product_id" in schema["properties"]
    assert "quantity" in schema["properties"]
    assert "customer_id" in schema["required"]
    assert "product_id" in schema["required"]


@pytest.mark.anyio
async def test_mcp_server_call_tool_async_approved():
    """
    Executes propose_purchase tool via the asynchronous MCP protocol call_tool method.
    """
    server = create_mcp_server()

    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        result = await server.call_tool(
            name="propose_purchase",
            arguments={"customer_id": "CUST001", "product_id": "KB001", "quantity": 1},
        )

    assert result.is_error is False
    assert len(result.content) == 1
    content_text = result.content[0].text
    data = json.loads(content_text)

    assert data["decision"] == "APPROVED"
    assert data["product_id"] == "KB001"
    assert data["amount"] == 1499.0
    assert data["payment"]["status"] == "created"
    assert data["payment"]["razorpay_order_id"] == "order_MCPTest_ABC123"


@pytest.mark.anyio
async def test_mcp_server_call_tool_async_rejected():
    """
    Executes propose_purchase for an over-limit item via MCP protocol.
    """
    server = create_mcp_server()

    with patch(_CREATE_ORDER) as mock_create:
        result = await server.call_tool(
            name="propose_purchase",
            arguments={"customer_id": "CUST001", "product_id": "MN001", "quantity": 1},
        )

    mock_create.assert_not_called()
    assert result.is_error is False
    data = json.loads(result.content[0].text)
    assert data["decision"] == "REJECTED"
    assert data["payment"] is None
    assert "exceeds maximum mandate limit" in data["reason"]

"""
Tests for Phase 4 & Phase 7 — Model Context Protocol (MCP) Wrapper & Data Minimization.

Verifies:
1. Tool handler unit tests with minimized customer-facing response shapes.
2. Canonical approved (KB001) and rejected (MN001) flows over MCP.
3. Multi-merchant cross-merchant approval (FD001) and rejection (CUST002).
4. Error handling: unknown product, unknown customer, invalid quantity, and stock exceeded return structured rejection.
5. Product search handler and async tool execution.
6. Data confidentiality: raw transaction_id and razorpay_order_id are never exposed over MCP.
7. Full audit trail persistence: admin audit logs retain complete tracing and IDs.
"""
import json
from unittest.mock import patch
import pytest

from app.audit import audit_store
from app.mcp.server import (
    create_mcp_server,
    mcp_server,
)
from app.mcp.tools import (
    propose_purchase_handler,
    resolve_customer_handler,
    search_products_handler,
    to_customer_response,
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


# ══════════════════════════════════════════════════════════════════════════════
# 1. MCP Tool Handler Unit Tests (Data-Minimized Shape)
# ══════════════════════════════════════════════════════════════════════════════

def test_mcp_tool_approved_canonical():
    """
    CUST001 + KB001 (₹1,499 <= ₹2,000) -> APPROVED.
    Asserts data minimization: returns minimal customer fields, omitting raw IDs.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        result = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    mock_create.assert_called_once()
    assert result["decision"] == "APPROVED"
    assert result["product_name"] == "Mechanical Gaming Keyboard"
    assert result["amount"] == 1499.0
    assert "within mandate limit" in result["reason"]
    assert result["reference_code"] is not None
    assert result["reference_code"].startswith("REF-")

    # Data minimization asserts: internal IDs must NEVER be in MCP response
    assert "transaction_id" not in result
    assert "razorpay_order_id" not in result
    assert "payment" not in result
    assert "mandate_limit" not in result


def test_mcp_tool_rejected_over_limit_canonical():
    """
    CUST001 + MN001 (₹4,999 > ₹2,000) -> REJECTED.
    Asserts data minimization and rejection fields.
    """
    with patch(_CREATE_ORDER) as mock_create:
        result = propose_purchase_handler(
            customer_id="CUST001",
            product_id="MN001",
            quantity=1,
        )

    mock_create.assert_not_called()
    assert result["decision"] == "REJECTED"
    assert result["product_name"] == "27-inch 4K UHD Monitor"
    assert result["amount"] == 4999.0
    assert "exceeds maximum mandate limit" in result["reason"]
    assert result["reference_code"] is None

    # Data minimization asserts
    assert "transaction_id" not in result
    assert "razorpay_order_id" not in result
    assert "payment" not in result


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
    assert result["product_name"] == "Cold-Pressed Virgin Coconut Oil (500ml)"
    assert result["amount"] == 349.0
    assert result["reference_code"] is not None
    assert "transaction_id" not in result


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
    assert result["reference_code"] is None
    assert "transaction_id" not in result


def test_mcp_tool_unknown_product_returns_structured_rejection():
    """
    Unknown product ID returns a structured REJECTED response instead of crashing.
    """
    result = propose_purchase_handler(
        customer_id="CUST001",
        product_id="NON_EXISTENT_PROD",
        quantity=1,
    )
    assert result["decision"] == "REJECTED"
    assert "NON_EXISTENT_PROD" in result["reason"]
    assert result["reference_code"] is None


def test_mcp_tool_unknown_customer_returns_structured_rejection():
    """
    Unknown customer ID returns a structured REJECTED response instead of crashing.
    """
    result = propose_purchase_handler(
        customer_id="NON_EXISTENT_CUST",
        product_id="KB001",
        quantity=1,
    )
    assert result["decision"] == "REJECTED"
    assert "NON_EXISTENT_CUST" in result["reason"]
    assert result["reference_code"] is None


def test_mcp_tool_invalid_quantity_returns_structured_rejection():
    """
    Invalid quantity (e.g. 0 or negative) returns a structured REJECTED response.
    """
    result = propose_purchase_handler(
        customer_id="CUST001",
        product_id="KB001",
        quantity=0,
    )
    assert result["decision"] == "REJECTED"
    assert "Quantity must be a positive integer" in result["reason"]


def test_mcp_tool_stock_exceeded_returns_structured_rejection():
    """
    Requesting quantity exceeding stock returns a structured REJECTED response.
    """
    result = propose_purchase_handler(
        customer_id="CUST001",
        product_id="KB001",
        quantity=50,  # stock is 20
    )
    assert result["decision"] == "REJECTED"
    assert "exceeds available inventory" in result["reason"]


# ══════════════════════════════════════════════════════════════════════════════
# 2. Product Search & Catalog MCP Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_search_products_handler_by_query():
    """
    Search products handler returns matches containing query substring with minimal customer fields.
    """
    results = search_products_handler(query="keyboard")
    assert len(results) == 1
    assert results[0]["id"] == "KB001"
    assert "Keyboard" in results[0]["name"]
    assert results[0]["price"] == 1499.0
    assert results[0]["category"] == "electronics"
    # Internal merchant_id excluded from minimized search result
    assert "merchant_id" not in results[0]


def test_search_products_handler_with_filters():
    """
    Search products handler filters by category and max_price.
    """
    results = search_products_handler(category="electronics", max_price=2000.0)
    returned_ids = [p["id"] for p in results]
    assert "KB001" in returned_ids
    assert "MN001" not in returned_ids


# ══════════════════════════════════════════════════════════════════════════════
# 3. MCP Server Protocol Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_mcp_server_lists_all_tools():
    """
    Inspects tools exposed by the MCP server and verifies schemas and instructions.
    """
    server = create_mcp_server()
    tools = await server.list_tools()

    tool_names = [t.name for t in tools]
    assert "inquire_merchant" in tool_names
    assert "search_products" in tool_names
    assert "resolve_customer" in tool_names
    assert "propose_purchase" in tool_names
    # Admin tools MUST NOT be registered on MCP
    assert "create_customer" not in tool_names
    assert "update_mandate_limit" not in tool_names

    # Verify resolve_customer description and schema
    resolve_tool = next(t for t in tools if t.name == "resolve_customer")
    assert "Resolve a customer's display name or email" in resolve_tool.description
    resolve_schema = getattr(resolve_tool, "input_schema", getattr(resolve_tool, "inputSchema", {}))
    assert "identifier" in resolve_schema["properties"]

    # Verify search_products description and schema
    search_tool = next(t for t in tools if t.name == "search_products")
    assert "Call this before propose_purchase" in search_tool.description
    assert "Never ask the customer for a product ID directly" in search_tool.description
    search_schema = getattr(search_tool, "input_schema", getattr(search_tool, "inputSchema", {}))
    assert "query" in search_schema["properties"]
    assert "category" in search_schema["properties"]
    assert "max_price" in search_schema["properties"]

    # Verify propose_purchase description
    propose_tool = next(t for t in tools if t.name == "propose_purchase")
    assert "This only proposes a purchase for policy evaluation" in propose_tool.description
    propose_schema = getattr(propose_tool, "input_schema", getattr(propose_tool, "inputSchema", {}))
    assert "customer_id" in propose_schema["properties"]
    assert "product_id" in propose_schema["properties"]


@pytest.mark.anyio
async def test_mcp_server_call_search_products_async():
    """
    Executes search_products tool via asynchronous MCP protocol call_tool method.
    """
    server = create_mcp_server()
    result = await server.call_tool(
        name="search_products",
        arguments={"query": "keyboard"},
    )
    assert result.is_error is False
    assert len(result.content) >= 1
    items = [json.loads(c.text) for c in result.content]
    assert len(items) == 1
    assert items[0]["id"] == "KB001"
    assert "Keyboard" in items[0]["name"]


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
    assert data["product_name"] == "Mechanical Gaming Keyboard"
    assert data["amount"] == 1499.0
    assert data["reference_code"].startswith("REF-")
    assert "transaction_id" not in data
    assert "razorpay_order_id" not in data
    assert "payment" not in data


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
    assert data["product_name"] == "27-inch 4K UHD Monitor"
    assert data["reference_code"] is None
    assert "exceeds maximum mandate limit" in data["reason"]
    assert "transaction_id" not in data


# ══════════════════════════════════════════════════════════════════════════════
# 4. Data Confidentiality & Full Audit Trail Preservation
# ══════════════════════════════════════════════════════════════════════════════

def test_mcp_minimization_preserves_full_audit_trail():
    """
    Verifies that while the MCP client receives a strictly minimized payload,
    the underlying gateway records the full transaction UUID and Razorpay order ID
    in the admin audit trail.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        mcp_res = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    # 1. MCP response has no transaction_id or razorpay_order_id
    assert "transaction_id" not in mcp_res
    assert "razorpay_order_id" not in mcp_res
    ref_code = mcp_res["reference_code"]
    assert ref_code is not None and ref_code.startswith("REF-")
    ref_suffix = ref_code.replace("REF-", "").lower()

    # 2. Audit store contains full record with full UUID and Razorpay Order ID
    records = audit_store.list(customer_id="CUST001")
    assert len(records) >= 1
    latest_record = records[0]

    assert latest_record.transaction_id.endswith(ref_suffix)
    assert latest_record.razorpay_order_id == "order_MCPTest_ABC123"
    assert latest_record.merchant_id == "MERCH_ELEC"
    assert latest_record.decision == "APPROVED"


def test_mcp_tool_idempotency_within_60s_window():
    """
    Calling propose_purchase via MCP twice within the same 60-second window
    results in exactly ONE Razorpay order and returns the cached response.
    """
    with patch("time.time", return_value=1700000040.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        res1 = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    with patch("time.time", return_value=1700000050.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create2:
        res2 = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    assert res1["decision"] == "APPROVED"
    assert res2["decision"] == "APPROVED"
    assert res1["reference_code"] == res2["reference_code"]
    mock_create.assert_called_once()
    mock_create2.assert_not_called()

    # Verify audit store contains exactly 1 row
    records = audit_store.list(customer_id="CUST001")
    assert len(records) == 1


def test_mcp_tool_idempotency_rolls_over_past_60s():
    """
    Calling propose_purchase via MCP across 60-second window boundary
    generates a new transaction and makes a second Razorpay order call.
    """
    with patch("time.time", return_value=1700000040.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create1:
        res1 = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    with patch("time.time", return_value=1700000120.0), patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create2:
        res2 = propose_purchase_handler(
            customer_id="CUST001",
            product_id="KB001",
            quantity=1,
        )

    assert res1["decision"] == "APPROVED"
    assert res2["decision"] == "APPROVED"
    assert res1["reference_code"] != res2["reference_code"]
    mock_create1.assert_called_once()
    mock_create2.assert_called_once()

    # Verify audit store contains 2 distinct rows
    records = audit_store.list(customer_id="CUST001")
    assert len(records) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 5. Customer Identity Resolution Tests (resolve_customer)
# ══════════════════════════════════════════════════════════════════════════════

def test_resolve_customer_exact_display_name_match():
    """
    Exact display_name match returns resolved=True with customer_id and display_name.
    """
    res1 = resolve_customer_handler("Dinesh Kumar")
    assert res1["resolved"] is True
    assert res1["customer_id"] == "CUST001"
    assert res1["display_name"] == "Dinesh Kumar"

    res2 = resolve_customer_handler("Alex Smith")
    assert res2["resolved"] is True
    assert res2["customer_id"] == "CUST002"
    assert res2["display_name"] == "Alex Smith"


def test_resolve_customer_case_insensitive_partial_match():
    """
    Case-insensitive partial match resolves successfully.
    """
    res1 = resolve_customer_handler("dinesh")
    assert res1["resolved"] is True
    assert res1["customer_id"] == "CUST001"
    assert res1["display_name"] == "Dinesh Kumar"

    res2 = resolve_customer_handler("ALEX")
    assert res2["resolved"] is True
    assert res2["customer_id"] == "CUST002"


def test_resolve_customer_email_match():
    """
    Exact email match resolves successfully.
    """
    res = resolve_customer_handler("dinesh@example.com")
    assert res["resolved"] is True
    assert res["customer_id"] == "CUST001"


def test_resolve_customer_no_match_structured_rejection():
    """
    Non-existent name or email returns structured no_match rejection without raising an exception.
    """
    res = resolve_customer_handler("Unknown Person")
    assert res["resolved"] is False
    assert res["reason"] == "no_match"
    assert "No authorized customer found" in res["message"]

    res_empty = resolve_customer_handler("")
    assert res_empty["resolved"] is False
    assert res_empty["reason"] == "no_match"


def test_resolve_customer_ambiguous_match_returns_candidates():
    """
    When multiple customers match a query (e.g. 'Dinesh'), resolve_customer returns
    resolved=False with reason='ambiguous' and lists candidate names for clarification.
    """
    from app.policy.store import mandate_store
    from app.policy.mandate import Mandate

    # Temporarily seed a second 'Dinesh'
    colliding_mandate = Mandate(
        customer_id="CUST999",
        display_name="Dinesh Sharma",
        email="dinesh.sharma@example.com",
        max_transaction_amount=3000.0,
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
    )
    mandate_store.save_mandate(colliding_mandate)

    try:
        res = resolve_customer_handler("Dinesh")
        assert res["resolved"] is False
        assert res["reason"] == "ambiguous"
        assert set(res["candidates"]) == {"Dinesh Kumar", "Dinesh Sharma"}
        assert "Multiple customers found" in res["message"]

        # Exact full name still resolves uniquely
        exact_res = resolve_customer_handler("Dinesh Sharma")
        assert exact_res["resolved"] is True
        assert exact_res["customer_id"] == "CUST999"
    finally:
        # Cleanup
        mandate_store.delete_mandate("CUST999")


def test_mcp_flow_resolve_then_propose_canonical_kb001_and_mn001():
    """
    End-to-end multi-step flow:
    1. AI resolves 'Dinesh' -> gets CUST001
    2. Proposes KB001 (₹1,499) -> APPROVED
    3. Proposes MN001 (₹4,999) -> REJECTED (over ₹2,000 limit)
    Verifies amounts, limits, and policy decisions are identical to direct CUST001 calls.
    """
    # Step 1: Resolve identity
    id_res = resolve_customer_handler("Dinesh")
    assert id_res["resolved"] is True
    cust_id = id_res["customer_id"]
    assert cust_id == "CUST001"

    # Step 2: Propose approved purchase
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        approved_res = propose_purchase_handler(
            customer_id=cust_id,
            product_id="KB001",
            quantity=1,
        )
    mock_create.assert_called_once()
    assert approved_res["decision"] == "APPROVED"
    assert approved_res["amount"] == 1499.0
    assert approved_res["reference_code"].startswith("REF-")

    # Step 3: Propose rejected purchase (over limit)
    with patch(_CREATE_ORDER) as mock_create_none:
        rejected_res = propose_purchase_handler(
            customer_id=cust_id,
            product_id="MN001",
            quantity=1,
        )
    mock_create_none.assert_not_called()
    assert rejected_res["decision"] == "REJECTED"
    assert rejected_res["amount"] == 4999.0
    assert "exceeds maximum mandate limit" in rejected_res["reason"]


@pytest.mark.anyio
async def test_mcp_server_call_resolve_customer_async():
    """
    Executes resolve_customer tool via asynchronous MCP protocol call_tool method.
    """
    server = create_mcp_server()
    result = await server.call_tool(
        name="resolve_customer",
        arguments={"identifier": "Dinesh Kumar"},
    )
    assert result.is_error is False
    assert len(result.content) == 1
    data = json.loads(result.content[0].text)
    assert data["resolved"] is True
    assert data["customer_id"] == "CUST001"
    assert data["display_name"] == "Dinesh Kumar"


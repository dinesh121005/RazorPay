"""
Tests for Merchant-Side Sales AI Agent (Agent-to-Agent Commerce).
"""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp.tools import inquire_merchant_handler, propose_purchase_handler
from app.merchant_agent.models import InquiryRequest
from app.merchant_agent.service import merchant_agent_service

client = TestClient(app)

_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_A2A_12345",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "a2a-receipt-999",
}


def test_merchant_agent_semantic_clicky_keyboard_match():
    """
    Merchant Agent semantically maps 'clicky keyboard for coding' to KB001 (tactile blue switches).
    """
    req = InquiryRequest(
        query="I need a clicky mechanical keyboard for coding",
        max_budget=2000.0,
        quantity=1,
    )
    res = merchant_agent_service.process_inquiry(req)

    assert res.total_matches >= 1
    assert res.best_match_product_id == "KB001"
    top_quote = res.quotes[0]
    assert top_quote.product_id == "KB001"
    assert top_quote.price_per_unit == 1499.0
    assert top_quote.in_stock is True
    assert top_quote.within_budget is True
    # Verify semantic explanation in match reasons
    reasons_str = " ".join(top_quote.match_reasons).lower()
    assert "blue switches" in reasons_str or "tactile" in reasons_str


def test_merchant_agent_budget_filtering():
    """
    Merchant Agent accurately identifies when a product exceeds the buyer's budget.
    """
    req = InquiryRequest(
        query="4k monitor",
        max_budget=3000.0,
        quantity=1,
    )
    res = merchant_agent_service.process_inquiry(req)

    assert res.total_matches >= 1
    quote = next(q for q in res.quotes if q.product_id == "MN001")
    assert quote.within_budget is False
    assert "exceeds" in " ".join(quote.match_reasons).lower()


def test_merchant_agent_out_of_stock_quantity():
    """
    Merchant Agent flags quotes where requested quantity exceeds on-hand stock.
    """
    req = InquiryRequest(
        query="keyboard",
        quantity=100,  # stock is 20
    )
    res = merchant_agent_service.process_inquiry(req)

    assert res.total_matches >= 1
    quote = next(q for q in res.quotes if q.product_id == "KB001")
    assert quote.in_stock is False
    assert "insufficient stock" in " ".join(quote.match_reasons).lower()


def test_merchant_agent_no_match():
    """
    Merchant Agent handles queries with no catalog matches gracefully.
    """
    req = InquiryRequest(
        query="completely nonexistent hoverboard spaceship",
    )
    res = merchant_agent_service.process_inquiry(req)

    assert res.total_matches == 0
    assert res.best_match_product_id is None
    assert res.quotes == []
    assert "No matching products found" in res.merchant_notes


def test_merchant_inquire_rest_endpoint():
    """
    POST /merchant/inquire REST endpoint handles external Buyer AI requests.
    """
    payload = {
        "query": "organic coconut oil",
        "max_budget": 500.0,
        "quantity": 1,
    }
    response = client.post("/merchant/inquire", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["best_match_product_id"] == "FD001"
    assert len(data["quotes"]) >= 1
    assert data["quotes"][0]["name"] == "Cold-Pressed Virgin Coconut Oil (500ml)"
    assert data["quotes"][0]["total_price"] == 349.0


def test_mcp_inquire_merchant_tool():
    """
    inquire_merchant MCP tool handler returns structured dictionary for Claude.
    """
    result = inquire_merchant_handler(
        query="stainless steel water bottle",
        max_budget=1000.0,
        quantity=1,
    )
    assert result["best_match_product_id"] == "HK002"
    assert result["total_matches"] >= 1
    assert "quotes" in result


def test_end_to_end_a2a_inquiry_then_purchase():
    """
    Full Agent-to-Agent flow:
    1. Buyer Agent consults Merchant Agent via inquire_merchant.
    2. Merchant Agent returns quote for KB001.
    3. Buyer Agent submits purchase proposal for KB001 under CUST001's mandate -> PENDING_CONFIRMATION (>= ₹500).
    4. Buyer Agent / Customer executes confirm_purchase -> APPROVED with Razorpay Test Mode order.
    """
    from app.mcp.tools import confirm_purchase_handler

    # Step 1: Buyer Agent consults Merchant Agent
    inquiry_res = inquire_merchant_handler(
        query="clicky gaming keyboard",
        max_budget=2000.0,
    )
    assert inquiry_res["best_match_product_id"] == "KB001"
    recommended_product_id = inquiry_res["best_match_product_id"]

    # Step 2: Buyer Agent proposes purchase for the recommended product (Gated)
    with patch(_CREATE_ORDER) as mock_create_none:
        purchase_res = propose_purchase_handler(
            customer_id="CUST001",
            product_id=recommended_product_id,
            quantity=1,
        )

    mock_create_none.assert_not_called()
    assert purchase_res["decision"] == "PENDING_CONFIRMATION"
    assert purchase_res["requires_confirmation"] is True
    token = purchase_res["confirmation_token"]

    # Step 3: Confirm purchase
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_create:
        conf_res = confirm_purchase_handler(
            confirmation_token=token,
            customer_id="CUST001",
        )

    mock_create.assert_called_once()
    assert conf_res["decision"] == "APPROVED"
    assert conf_res["product_name"] == "Mechanical Gaming Keyboard"
    assert conf_res["amount"] == 1499.0
    assert conf_res["reference_code"].startswith("REF-")



def test_merchant_agent_llm_reasoning_pipeline():
    """
    Verifies that when LLM reasoning returns a structured quote, the service parses it directly.
    """
    mock_llm_quote = {
        "best_match_product_id": "KB001",
        "merchant_notes": "AI Sales Agent: The Mechanical Gaming Keyboard (KB001) is ideal for your request.",
        "quotes": [
            {
                "product_id": "KB001",
                "name": "Mechanical Gaming Keyboard",
                "category": "electronics",
                "price_per_unit": 1499.0,
                "total_price": 1499.0,
                "in_stock": True,
                "stock_available": 20,
                "match_reasons": ["Selected by Generative AI Sales Model"],
                "within_budget": True,
            }
        ],
    }

    with patch("app.merchant_agent.service.call_llm_merchant_reasoning", return_value=mock_llm_quote), patch("app.merchant_agent.llm.call_llm_merchant_reasoning", return_value=mock_llm_quote):
        req = InquiryRequest(query="i want keyboard")
        res = merchant_agent_service.process_inquiry(req)

    assert res.best_match_product_id == "KB001"
    assert "AI Sales Agent" in res.merchant_notes
    assert res.quotes[0].match_reasons == ["Selected by Generative AI Sales Model"]


def test_merchant_agent_llm_quote_grounding_interceptor():
    """
    Ensures LLM hallucinations (fake products or incorrect prices) are grounded against PRODUCTS:
    - Hallucinated products are dropped.
    - Hallucinated prices are overwritten with true catalog prices.
    """
    hallucinated_quote = {
        "best_match_product_id": "KB001",
        "merchant_notes": "Hallucinated response",
        "quotes": [
            {
                "product_id": "KB001",
                "name": "Mechanical Gaming Keyboard",
                "category": "electronics",
                "price_per_unit": 99.0,  # Hallucinated price! Real is 1499.0
                "total_price": 99.0,
                "in_stock": True,
                "stock_available": 999,  # Hallucinated stock! Real is 20
                "match_reasons": ["Hallucinated"],
                "within_budget": True,
            },
            {
                "product_id": "FAKE_NONEXISTENT_PROD",  # Unknown product
                "name": "Magic Wand",
                "category": "magic",
                "price_per_unit": 10.0,
                "total_price": 10.0,
                "in_stock": True,
                "stock_available": 10,
                "match_reasons": ["Fake"],
                "within_budget": True,
            }
        ],
    }

    with patch("app.merchant_agent.service.call_llm_merchant_reasoning", return_value=hallucinated_quote), patch("app.merchant_agent.llm.call_llm_merchant_reasoning", return_value=hallucinated_quote):
        req = InquiryRequest(query="i want keyboard")
        res = merchant_agent_service.process_inquiry(req)

    assert res.best_match_product_id == "KB001"
    assert len(res.quotes) == 1
    from app.catalog.service import get_product
    real_stock = get_product("KB001").stock
    assert res.quotes[0].stock_available == real_stock



def test_merchant_agent_recommend_addons():
    """
    Track 01 Revenue Growth: verifies add-on cross-sell suggestions.
    """
    res = merchant_agent_service.recommend_addons(product_id="KB001", remaining_budget=500.0)
    assert res.base_product_id == "KB001"
    assert len(res.addons) > 0
    for addon in res.addons:
        assert addon.price_per_unit <= 500.0




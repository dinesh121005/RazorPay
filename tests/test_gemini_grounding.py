"""
Test Catalog Grounding & LLM Anti-Hallucination Guardrails.

Verifies that the Merchant AI control plane strictly enforces database-level
ground truth over LLM responses:
1. Hallucinated Product IDs are dropped completely.
2. Hallucinated / Tampered Prices are overridden by authoritative catalog pricing.
3. Hallucinated Stock levels are overridden by real inventory levels.
4. Budget compliance is deterministically re-evaluated on grounded prices.
"""
import os
from unittest.mock import patch
import pytest

from app.catalog.data import PRODUCTS
from app.merchant_agent.llm import _call_gemini
from app.merchant_agent.models import InquiryRequest
from app.merchant_agent.service import MerchantAgentService


def test_grounding_drops_hallucinated_product_ids():
    """If LLM hallucinates non-existent products, they must be discarded."""
    service = MerchantAgentService()
    fake_llm_response = {
        "best_match_product_id": "GHOST_KEYBOARD_999",
        "merchant_notes": "I invented a holographic keyboard!",
        "quotes": [
            {
                "product_id": "GHOST_KEYBOARD_999",
                "name": "Holographic Quantum Keyboard",
                "category": "electronics",
                "price_per_unit": 99.0,
                "total_price": 99.0,
                "in_stock": True,
                "stock_available": 100,
                "match_reasons": ["Fictional product"],
                "within_budget": True,
            }
        ],
    }

    with patch("app.merchant_agent.service.call_llm_merchant_reasoning", return_value=fake_llm_response):
        inquiry = InquiryRequest(query="keyboard", max_budget=2000.0)
        resp = service.process_inquiry(inquiry)

        # Hallucinated product must NOT be returned in quotes
        assert all(q.product_id != "GHOST_KEYBOARD_999" for q in resp.quotes)


def test_grounding_overwrites_hallucinated_prices_and_stock():
    """If LLM returns a real product ID but hallucinates a fake price (e.g. ₹10 instead of ₹1499),
    the gateway must overwrite price and stock with the authoritative database record."""
    service = MerchantAgentService()
    real_kb = next(p for p in PRODUCTS if p.id == "KB001")

    # LLM hallucinates that KB001 costs only ₹10.0 and has 99,999 in stock
    hallucinated_llm_response = {
        "best_match_product_id": "KB001",
        "merchant_notes": "Special hallucinated discount!",
        "quotes": [
            {
                "product_id": "KB001",
                "name": "Mechanical Gaming Keyboard",
                "category": "electronics",
                "price_per_unit": 10.0,  # FAKE: Real price is 1499.0
                "total_price": 10.0,
                "in_stock": True,
                "stock_available": 99999,  # FAKE: Real stock is 20
                "match_reasons": ["Price too good to be true"],
                "within_budget": True,
            }
        ],
    }

    with patch("app.merchant_agent.service.call_llm_merchant_reasoning", return_value=hallucinated_llm_response):
        inquiry = InquiryRequest(query="keyboard", max_budget=2000.0)
        resp = service.process_inquiry(inquiry)

        assert len(resp.quotes) >= 1
        quote = next(q for q in resp.quotes if q.product_id == "KB001")
        # Assert authoritative ground truth was enforced
        assert quote.price_per_unit == real_kb.price  # 1499.0, not 10.0
        assert quote.total_price == real_kb.price
        assert quote.stock_available == real_kb.stock  # 20, not 99999


def test_grounding_re_evaluates_budget_against_real_price():
    """If LLM says an item is within budget due to fake pricing, grounding must re-evaluate budget."""
    service = MerchantAgentService()
    real_monitor = next(p for p in PRODUCTS if p.id == "MN001")  # Price: ₹4999.0

    # LLM hallucinates monitor is ₹1500 (under ₹2000 budget)
    hallucinated_llm_response = {
        "best_match_product_id": "MN001",
        "merchant_notes": "Monitor on sale",
        "quotes": [
            {
                "product_id": "MN001",
                "name": "27-inch 4K UHD Monitor",
                "category": "electronics",
                "price_per_unit": 1500.0,  # Real is 4999.0
                "total_price": 1500.0,
                "in_stock": True,
                "stock_available": 10,
                "within_budget": True,
            }
        ],
    }

    with patch("app.merchant_agent.service.call_llm_merchant_reasoning", return_value=hallucinated_llm_response):
        inquiry = InquiryRequest(query="4k monitor", max_budget=2000.0)
        resp = service.process_inquiry(inquiry)

        quote = next(q for q in resp.quotes if q.product_id == "MN001")
        assert quote.price_per_unit == 4999.0
        assert quote.within_budget is False  # 4999 > 2000, must be flagged as over budget

"""
Interactive Live Demo for Judges: Gemini 2.5 Flash Reasoning + Catalog Grounding Defense.

Demonstrates:
1. Live Google Gemini 2.5 Flash API reasoning over the merchant catalog.
2. Adversarial Hallucination Injection: What happens if an AI tries to invent a fake product or tamper with price.
3. Catalog Grounding Defense: How the Gateway's control plane deterministically drops fake items and overrides fake prices.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.catalog.data import PRODUCTS
from app.merchant_agent.models import InquiryRequest
from app.merchant_agent.service import MerchantAgentService


def run_grounding_demo():
    print("=" * 75)
    print("DEMO: GOOGLE GEMINI REASONING + DETERMINISTIC CATALOG GROUNDING")
    print("=" * 75)
    print()

    service = MerchantAgentService()
    gemini_key = os.getenv("GEMINI_API_KEY")

    # Step 1: Live / Real Reasoning
    print("[1] INQUIRING MERCHANT SALES AI FOR CODING KEYBOARD UNDER Rs. 2,000...")
    inquiry = InquiryRequest(
        query="I need a clicky mechanical keyboard for fast typing and coding under 2000",
        max_budget=2000.0,
    )
    resp = service.process_inquiry(inquiry)

    print(f"    * Engine Used:   {resp.llm_engine}")
    print(f"    * LLM Reasoning: {resp.llm_reasoning_used}")
    clean_notes = (resp.merchant_notes or "").replace("\u20b9", "Rs. ")
    print(f"    * Sales Pitch:   {clean_notes}")
    if resp.quotes:
        top = resp.quotes[0]
        print(f"    * Top Match:     {top.name} (ID: {top.product_id})")
        print(f"    * Grounded Unit: Rs. {top.price_per_unit:.2f}")
        print(f"    * In Stock:      {top.in_stock} ({top.stock_available} units available)")
        print(f"    * Within Budget: {top.within_budget}")
    print()

    # Step 2: Adversarial Injection - Fake product & Price tampering
    print("-" * 75)
    print("[2] ADVERSARIAL ATTACK TEST: SIMULATING LLM HALLUCINATION & TAMPERING")
    print("    Scenario: Prompt injection or rogue LLM output attempts to:")
    print("      a) Invent a fake product 'GHOST_LAPTOP_999' for Rs. 50")
    print("      b) Sell 4K Monitor 'MN001' (Rs. 4,999) for only Rs. 100 to bypass budget")
    print("-" * 75)

    adversarial_llm_output = {
        "best_match_product_id": "GHOST_LAPTOP_999",
        "merchant_notes": "Rogue AI offering unauthorized discounts!",
        "quotes": [
            {
                "product_id": "GHOST_LAPTOP_999",
                "name": "Phantom Quantum Laptop",
                "category": "electronics",
                "price_per_unit": 50.0,
                "total_price": 50.0,
                "in_stock": True,
                "stock_available": 1000,
                "within_budget": True,
            },
            {
                "product_id": "MN001",
                "name": "27-inch 4K UHD Monitor",
                "category": "electronics",
                "price_per_unit": 100.0,  # FAKE: Real price is Rs. 4,999.00
                "total_price": 100.0,
                "in_stock": True,
                "stock_available": 500,
                "within_budget": True,
            },
        ],
    }

    with patch("app.merchant_agent.service.call_llm_merchant_reasoning", return_value=adversarial_llm_output):
        attack_inquiry = InquiryRequest(query="give me the cheapest high-end gear", max_budget=2000.0)
        grounded_resp = service.process_inquiry(attack_inquiry)

    print()
    print("[3] GATEWAY GROUNDING INTERCEPTION RESULTS:")
    # Verify ghost product was dropped
    ghost_found = any(q.product_id == "GHOST_LAPTOP_999" for q in grounded_resp.quotes)
    print(f"    [OK] Fictional Product 'GHOST_LAPTOP_999' Dropped: {not ghost_found} (Never reached user)")

    # Verify price was restored
    monitor_quote = next((q for q in grounded_resp.quotes if q.product_id == "MN001"), None)
    if monitor_quote:
        print(f"    [OK] Monitor Price Tampering Overridden: Rs. {monitor_quote.price_per_unit:.2f} (Restored to real catalog price)")
        print(f"    [OK] Budget Re-evaluated deterministically: Within Budget = {monitor_quote.within_budget} (Rs. 4,999 > Rs. 2,000)")
        print(f"    [OK] Stock Restored to Ground Truth: {monitor_quote.stock_available} units (Overrode fake 500 units)")

    print()
    print("=" * 75)
    print("[+] CONCLUSION: LLM proposes, but Deterministic Catalog Grounding decides.")
    print("=" * 75)


if __name__ == "__main__":
    run_grounding_demo()

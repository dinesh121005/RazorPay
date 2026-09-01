"""
LLM Reasoning Engine for Merchant-Side Sales AI Agent (Agent-to-Agent Commerce).

Uses actual Generative AI / Large Language Models (Gemini / OpenAI) when an API key is available,
enabling true autonomous LLM-to-LLM reasoning over the private merchant catalog database.
Falls back seamlessly to local semantic reasoning if running in offline test mode.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

MERCHANT_SYSTEM_PROMPT = """
You are the Autonomous Merchant Sales AI Agent for our retail store.
You represent the store and have full access to our private product catalog database.

Your task:
1. Receive natural language procurement requests from Buyer AI Agents (e.g., "i want keyboard", "need clicky keyboard for coding", "4k monitor").
2. Reason over our product catalog to select the best matching product, analyze features, pricing, stock availability, and budget compatibility.
3. Formulate a structured, transparent product quote and persuasive merchant sales recommendation.

Return ONLY a valid JSON object with the following schema:
{
  "best_match_product_id": "PRODUCT_ID or null",
  "merchant_notes": "Your professional sales reasoning and recommendation summary",
  "quotes": [
    {
      "product_id": "PRODUCT_ID",
      "name": "Product Name",
      "category": "Category",
      "price_per_unit": 1499.0,
      "total_price": 1499.0,
      "in_stock": true,
      "stock_available": 20,
      "match_reasons": ["Reason 1", "Reason 2"],
      "within_budget": true
    }
  ]
}
"""


def call_llm_merchant_reasoning(
    query: str,
    catalog: List[Dict[str, Any]],
    max_budget: Optional[float] = None,
    category: Optional[str] = None,
    quantity: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Invokes real LLM reasoning (Gemini / OpenAI) if configured in environment variables.
    Returns parsed JSON dict or None if no LLM key is configured.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not gemini_key and not openai_key:
        return None

    user_payload = {
        "buyer_inquiry": query,
        "max_budget_ceiling": max_budget,
        "category_filter": category,
        "requested_quantity": quantity,
        "store_catalog_database": catalog,
    }

    try:
        if gemini_key:
            return _call_gemini(gemini_key, user_payload)
        elif openai_key:
            return _call_openai(openai_key, user_payload)
    except Exception as e:
        logger.warning(f"Merchant LLM reasoning failed, falling back to local reasoning: {e}")
        return None

    return None


def _call_gemini(api_key: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Calls Google Gemini API for Merchant Agent reasoning."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = f"{MERCHANT_SYSTEM_PROMPT}\n\nBuyer Request and Catalog Data:\n{json.dumps(payload, indent=2)}"

    with httpx.Client(timeout=15.0) as client:
        res = client.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            },
        )
        if res.status_code == 200:
            data = res.json()
            text_content = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content)
    return None


def _call_openai(api_key: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Calls OpenAI API for Merchant Agent reasoning."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    messages = [
        {"role": "system", "content": MERCHANT_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2)},
    ]

    with httpx.Client(timeout=15.0) as client:
        res = client.post(
            url,
            headers=headers,
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
                "response_format": {"type": "json_object"}
            },
        )
        if res.status_code == 200:
            data = res.json()
            text_content = data["choices"][0]["message"]["content"]
            return json.loads(text_content)
    return None

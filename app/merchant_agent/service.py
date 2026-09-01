"""
Merchant-Side Sales AI Agent service layer (Agent-to-Agent Commerce).

Analyzes natural language procurement inquiries from Buyer AI Agents (e.g. Claude),
reasons over private merchant catalog & stock using real Generative LLMs (or local semantic engine),
and formulates structured, transparent quotes.
"""
from typing import List, Optional

from app.catalog.data import PRODUCTS
from app.catalog.models import Product
from app.merchant_agent.llm import call_llm_merchant_reasoning
from app.merchant_agent.models import InquiryRequest, InquiryResponse, ProductQuote

# Semantic knowledge graph mapping colloquial buyer requirements to product specifications
SEMANTIC_FEATURE_MAP = {
    "clicky": ["tactile", "blue switches", "switches", "mechanical"],
    "gaming": ["rgb", "backlighting", "144hz", "mechanical", "gaming"],
    "coding": ["mechanical", "tactile", "switches", "compact"],
    "typing": ["mechanical", "tactile", "blue switches"],
    "4k": ["4k", "uhd", "ultra hd", "ips", "hdr10"],
    "monitor": ["display", "screen", "ips", "144hz", "hdr10"],
    "screen": ["display", "ips", "monitor", "4k"],
    "drink": ["mug", "bottle", "water", "coffee", "ceramic"],
    "coffee": ["ceramic", "heat-resistant", "mug"],
    "tea": ["ceramic", "heat-resistant", "mug"],
    "water": ["stainless steel", "insulated", "vacuum"],
    "bottle": ["insulated", "vacuum", "water bottle"],
    "healthy": ["organic", "unrefined", "whole grain", "dietary fibre"],
    "breakfast": ["oats", "rolled oats", "whole grain"],
    "oil": ["coconut oil", "cold-pressed", "virgin"],
    "clothes": ["cotton", "t-shirt", "crew neck", "apparel"],
    "apparel": ["cotton", "t-shirt", "crew neck"],
}


class MerchantAgentService:
    """
    Autonomous Merchant Sales AI Agent.
    Mediates catalog access, evaluates buyer queries, checks real-time inventory,
    and formulates structured quotes for Buyer Agents.
    """

    def process_inquiry(self, inquiry: InquiryRequest) -> InquiryResponse:
        """
        Processes a natural language inquiry from a Buyer Agent.
        Tries real LLM reasoning first; falls back to local semantic reasoning if offline.
        """
        # 1. Attempt Real LLM-based Merchant Reasoning if API key is configured
        catalog_dict = [p.model_dump() for p in PRODUCTS]
        llm_result = call_llm_merchant_reasoning(
            query=inquiry.query,
            catalog=catalog_dict,
            max_budget=inquiry.max_budget,
            category=inquiry.category,
            quantity=inquiry.quantity,
        )

        if llm_result and "quotes" in llm_result:
            try:
                quotes = [ProductQuote(**q) for q in llm_result.get("quotes", [])]
                best_id = llm_result.get("best_match_product_id") or (quotes[0].product_id if quotes else None)
                notes = llm_result.get("merchant_notes", "Merchant Agent Quote formulated via LLM reasoning.")
                return InquiryResponse(
                    best_match_product_id=best_id,
                    quotes=quotes,
                    merchant_notes=notes,
                    total_matches=len(quotes),
                )
            except Exception:
                pass  # Fall through to deterministic semantic analysis on parsing error

        # 2. Local Semantic Reasoning Engine (Offline / Unit Test fallback)
        return self._local_semantic_inquiry(inquiry)

    def _local_semantic_inquiry(self, inquiry: InquiryRequest) -> InquiryResponse:
        query_clean = inquiry.query.strip().lower()
        query_words = [w for w in query_clean.split() if w]
        requested_qty = max(1, inquiry.quantity)

        matched_quotes: List[ProductQuote] = []

        for p in PRODUCTS:
            # Check category filter if provided
            if inquiry.category and p.category.lower() != inquiry.category.strip().lower():
                continue

            match_score, reasons = self._evaluate_product_relevance(p, query_clean, query_words)

            if match_score > 0:
                total_price = round(p.price * requested_qty, 2)
                in_stock = p.stock >= requested_qty
                within_budget = True if inquiry.max_budget is None else total_price <= inquiry.max_budget

                if in_stock:
                    match_score += 10
                    reasons.append(f"{requested_qty} unit(s) available in stock ({p.stock} units on hand)")
                else:
                    reasons.append(f"Insufficient stock (only {p.stock} units available, requested {requested_qty})")

                if inquiry.max_budget is not None:
                    if within_budget:
                        reasons.append(f"Total ₹{total_price:.2f} is within requested budget ceiling of ₹{inquiry.max_budget:.2f}")
                    else:
                        match_score -= 20
                        reasons.append(f"Total ₹{total_price:.2f} exceeds requested budget ceiling of ₹{inquiry.max_budget:.2f}")

                quote = ProductQuote(
                    product_id=p.id,
                    name=p.name,
                    category=p.category,
                    price_per_unit=p.price,
                    total_price=total_price,
                    in_stock=in_stock,
                    stock_available=p.stock,
                    match_reasons=reasons,
                    within_budget=within_budget,
                )
                matched_quotes.append((match_score, quote))

        # Sort quotes by match score descending (best match first)
        matched_quotes.sort(key=lambda x: x[0], reverse=True)
        final_quotes = [q for _, q in matched_quotes]

        best_product_id = final_quotes[0].product_id if final_quotes else None

        if final_quotes:
            top_quote = final_quotes[0]
            if top_quote.within_budget and top_quote.in_stock:
                notes = (
                    f"Merchant Recommendation: {top_quote.name} ({top_quote.product_id}) "
                    f"is our top match at ₹{top_quote.total_price:.2f}. "
                    f"It is in stock and ready for purchase proposal."
                )
            elif not top_quote.within_budget:
                notes = (
                    f"Found {top_quote.name} ({top_quote.product_id}) at ₹{top_quote.total_price:.2f}, "
                    f"which exceeds the requested budget of ₹{inquiry.max_budget:.2f}."
                )
            else:
                notes = f"Found {top_quote.name} ({top_quote.product_id}), but requested quantity exceeds available stock."
        else:
            notes = f"No matching products found in the store catalog for '{inquiry.query}'."

        return InquiryResponse(
            best_match_product_id=best_product_id,
            quotes=final_quotes,
            merchant_notes=notes,
            total_matches=len(final_quotes),
        )

    def _evaluate_product_relevance(
        self,
        product: Product,
        query_text: str,
        query_words: List[str],
    ) -> tuple[int, List[str]]:
        """
        Evaluates relevance score and reasons why a product matches the buyer's inquiry.
        """
        score = 0
        reasons: List[str] = []
        name_lower = product.name.lower()
        desc_lower = (product.description or "").lower()
        full_text = f"{name_lower} {product.category.lower()} {desc_lower}"

        # 1. Exact name match
        if query_text in name_lower:
            score += 50
            reasons.append(f"Product name '{product.name}' directly matches search term")

        # 2. Word-level matches
        matched_words = [w for w in query_words if w in full_text]
        if matched_words:
            score += len(matched_words) * 15
            reasons.append(f"Matches keywords: {', '.join(matched_words)}")

        # 3. Semantic feature mappings (e.g. 'clicky' -> 'blue switches')
        for keyword, mapped_specs in SEMANTIC_FEATURE_MAP.items():
            if keyword in query_words or keyword in query_text:
                for spec in mapped_specs:
                    if spec in full_text:
                        score += 30
                        reasons.append(f"Requested feature '{keyword}' maps to product specification: '{spec}'")
                        break

        # 4. Description match
        if query_text in desc_lower and query_text not in name_lower:
            score += 25
            reasons.append(f"Product description matches: '{query_text}'")

        return score, reasons


merchant_agent_service = MerchantAgentService()

"""
Merchant-Side Sales AI Agent service layer (Agent-to-Agent Commerce).

Analyzes natural language procurement inquiries from Buyer AI Agents (e.g. Claude),
reasons over private merchant catalog & stock using real Generative LLMs (or local semantic engine),
and formulates structured, transparent quotes.
"""
from typing import Dict, List, Optional, Tuple

from app.catalog.data import PRODUCTS
from app.catalog.models import Product
from app.merchant_agent.llm import call_llm_merchant_reasoning
from app.merchant_agent.models import (
    AddOnRecommendationResponse,
    InquiryRequest,
    InquiryResponse,
    ProductQuote,
)

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
    "coffee": ["filter coffee", "kumbakonam", "degree", "peaberry", "ceramic", "heat-resistant", "mug"],
    "tea": ["nilgiri", "green tea", "black tea", "moringa", "infusion", "ceramic", "heat-resistant", "mug"],
    "water": ["stainless steel", "salem", "insulated", "vacuum"],
    "bottle": ["insulated", "vacuum", "water bottle", "salem"],
    "healthy": ["organic", "unrefined", "whole grain", "dietary fibre", "millet", "sathu maavu", "moringa"],
    "breakfast": ["oats", "rolled oats", "samai", "millet", "whole grain", "sathu maavu"],
    "oil": ["coconut oil", "cold-pressed", "virgin", "gingelly", "sesame", "mara chekku", "nalla ennai"],
    "snack": ["murukku", "kadalai mittai", "halwa", "palkova", "banana chips", "macaroons", "mixture", "seeval"],
    "sweets": ["halwa", "palkova", "kadalai mittai", "chocolates", "jaggery", "tirunelveli"],
    "sweet": ["halwa", "palkova", "kadalai mittai", "chocolates", "jaggery", "tirunelveli"],
    "spice": ["idli milagai podi", "podi", "gunpowder", "mango thokku", "pickle", "curry leaves", "chilli"],
    "rice": ["black rice", "karuppu kavuni", "heritage", "antioxidants"],
    "clothes": ["cotton", "t-shirt", "crew neck", "apparel", "tiruppur"],
    "apparel": ["cotton", "t-shirt", "crew neck", "tiruppur"],
}

# Cross-sell affinity graph mapping product IDs to complementary add-on product IDs
CROSS_SELL_AFFINITY_MAP: Dict[str, List[str]] = {
    "KB001": ["HK001", "HK002"],  # Mechanical Keyboard -> Ceramic Coffee Mug (for desk), Water Bottle
    "MN001": ["KB001", "HK001"],  # Monitor -> Mechanical Keyboard, Coffee Mug
    "HK001": ["FD007", "HK002", "AP001"],  # Coffee Mug -> Kumbakonam Filter Coffee, Water Bottle, T-Shirt
    "HK002": ["HK001", "AP001"],  # Water Bottle -> Coffee Mug, T-Shirt
    "HK005": ["FD007", "HK001"],  # French Press / Coffee Maker -> Kumbakonam Filter Coffee, Mug
    "HK006": ["FD016", "FD021"],  # Dosa Tawa -> Erode Sesame Oil, Madurai Idli Milagai Podi
    "FD001": ["FD002", "FD020"],  # Coconut Oil -> Rolled Oats & Millets, Banana Chips
    "FD002": ["FD001", "FD008"],  # Rolled Oats -> Coconut Oil, Marthandam Honey
    "FD007": ["HK001", "FD003", "FD011"],  # Kumbakonam Filter Coffee -> Coffee Mug, Kadalai Mittai, Murukku
    "FD011": ["FD005", "FD007"],  # Manapparai Murukku -> Tirunelveli Halwa, Filter Coffee
    "FD016": ["FD021", "FD012"],  # Sesame Oil -> Idli Milagai Podi, Karuppu Kavuni Rice
    "FD021": ["FD016", "HK006"],  # Idli Milagai Podi -> Gingelly Sesame Oil, Dosa Tawa
    "AP001": ["HK002", "HK001"],  # Apparel -> Water Bottle, Mug
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
        Strictly grounds all LLM quotes against the real catalog to prevent price/stock hallucinations.
        """
        # 1. Attempt Real LLM-based Merchant Reasoning if API key is configured
        catalog_dict = [p.model_dump() for p in PRODUCTS]
        catalog_by_id = {p.id: p for p in PRODUCTS}

        llm_result = call_llm_merchant_reasoning(
            query=inquiry.query,
            catalog=catalog_dict,
            max_budget=inquiry.max_budget,
            category=inquiry.category,
            quantity=inquiry.quantity,
        )

        if llm_result and "quotes" in llm_result:
            try:
                raw_quotes = llm_result.get("quotes", [])
                validated_quotes: List[ProductQuote] = []
                requested_qty = max(1, inquiry.quantity)

                for q_dict in raw_quotes:
                    pid = q_dict.get("product_id")
                    if not pid or pid not in catalog_by_id:
                        continue  # Drop hallucinated or non-existent product IDs

                    real_product = catalog_by_id[pid]
                    # Overwrite pricing and inventory with authoritative ground truth
                    total_price = round(real_product.price * requested_qty, 2)
                    in_stock = real_product.stock >= requested_qty
                    within_budget = True if inquiry.max_budget is None else total_price <= inquiry.max_budget

                    reasons = q_dict.get("match_reasons") or [
                        f"Recommended by Merchant AI for query: '{inquiry.query}'"
                    ]

                    validated_quote = ProductQuote(
                        product_id=real_product.id,
                        name=real_product.name,
                        category=real_product.category,
                        price_per_unit=real_product.price,
                        total_price=total_price,
                        in_stock=in_stock,
                        stock_available=real_product.stock,
                        match_reasons=reasons,
                        within_budget=within_budget,
                    )
                    validated_quotes.append(validated_quote)

                if validated_quotes:
                    best_id = llm_result.get("best_match_product_id")
                    if not best_id or best_id not in catalog_by_id:
                        best_id = validated_quotes[0].product_id

                    notes = llm_result.get(
                        "merchant_notes",
                        "Merchant Agent Quote formulated via LLM reasoning grounded in live catalog.",
                    )
                    return InquiryResponse(
                        best_match_product_id=best_id,
                        quotes=validated_quotes,
                        merchant_notes=notes,
                        total_matches=len(validated_quotes),
                    )
            except Exception:
                pass  # Fall through to deterministic semantic analysis on parsing error

        # 2. Local Semantic Reasoning Engine (Offline / Unit Test fallback)
        return self._local_semantic_inquiry(inquiry)

    def _local_semantic_inquiry(self, inquiry: InquiryRequest) -> InquiryResponse:
        query_clean = inquiry.query.strip().lower()
        query_words = [w for w in query_clean.split() if w]
        requested_qty = max(1, inquiry.quantity)

        matched_quotes: List[Tuple[int, ProductQuote]] = []

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

    def recommend_addons(
        self,
        product_id: str,
        remaining_budget: Optional[float] = None,
    ) -> AddOnRecommendationResponse:
        """
        Track 01 Revenue Growth Engine: Formulates intelligent cross-sell and add-on
        recommendations to increase merchant order basket value within mandate headroom.
        """
        clean_pid = product_id.strip()
        catalog_by_id = {p.id: p for p in PRODUCTS}
        base_product = catalog_by_id.get(clean_pid)

        # Determine complementary target product IDs
        candidate_ids = CROSS_SELL_AFFINITY_MAP.get(clean_pid, [])
        if not candidate_ids:
            # Fallback to other items in catalog
            candidate_ids = [p.id for p in PRODUCTS if p.id != clean_pid]

        addon_quotes: List[ProductQuote] = []
        for cid in candidate_ids:
            cand = catalog_by_id.get(cid)
            if not cand or cand.stock < 1:
                continue

            within_budget = True if remaining_budget is None else cand.price <= remaining_budget
            if remaining_budget is not None and not within_budget:
                continue  # Only recommend items that fit within customer's available headroom

            quote = ProductQuote(
                product_id=cand.id,
                name=cand.name,
                category=cand.category,
                price_per_unit=cand.price,
                total_price=cand.price,
                in_stock=True,
                stock_available=cand.stock,
                match_reasons=[
                    f"Complementary add-on pairing with {base_product.name if base_product else clean_pid}",
                    f"Fits within available budget headroom of ₹{remaining_budget:.2f}" if remaining_budget else "In stock for immediate dispatch",
                ],
                within_budget=within_budget,
            )
            addon_quotes.append(quote)

        pitch = (
            f"Merchant Sales Suggestion: Complete your setup with these recommended add-ons "
            f"designed to pair perfectly with {base_product.name if base_product else clean_pid}!"
            if addon_quotes
            else f"No add-ons currently available fitting within the remaining headroom limit."
        )

        return AddOnRecommendationResponse(
            base_product_id=clean_pid,
            addons=addon_quotes,
            merchant_pitch=pitch,
            total_addons=len(addon_quotes),
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


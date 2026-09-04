"""
Data models for Merchant-Side Sales AI Agent (Agent-to-Agent Commerce).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class InquiryRequest(BaseModel):
    """
    Inquiry payload sent by a Buyer AI Agent (e.g. Claude) to the Merchant Agent.
    """
    query: str = Field(..., description="Natural language procurement request (e.g. 'clicky mechanical keyboard for coding')")
    max_budget: Optional[float] = Field(default=None, description="Optional buyer budget ceiling in INR (₹)")
    category: Optional[str] = Field(default=None, description="Optional target product category")
    quantity: int = Field(default=1, ge=1, description="Desired quantity of units")


class ProductQuote(BaseModel):
    """
    Structured product quote formulated by the Merchant Agent.
    """
    product_id: str = Field(..., description="Catalog product ID")
    name: str = Field(..., description="Product display name")
    category: str = Field(..., description="Product category")
    price_per_unit: float = Field(..., description="Unit price in INR (₹)")
    total_price: float = Field(..., description="Total price for requested quantity in INR (₹)")
    in_stock: bool = Field(..., description="Whether requested quantity is in stock")
    stock_available: int = Field(..., description="Available inventory count")
    match_reasons: List[str] = Field(default_factory=list, description="Why this product matches the buyer's natural language requirements")
    within_budget: bool = Field(default=True, description="Whether total price is within buyer's requested budget")


class InquiryResponse(BaseModel):
    """
    Response returned by the Merchant Agent to the Buyer AI Agent.
    """
    best_match_product_id: Optional[str] = Field(default=None, description="Product ID of the top recommended quote")
    quotes: List[ProductQuote] = Field(default_factory=list, description="List of matched product quotes ranked by relevance")
    merchant_notes: str = Field(..., description="Summary message and recommendation from the Merchant Sales Agent")
    total_matches: int = Field(..., description="Number of matching products found")
    llm_reasoning_used: bool = Field(default=False, description="Whether live LLM reasoning (Gemini/OpenAI) generated this quote")
    llm_engine: Optional[str] = Field(default="Local Grounded Semantic Knowledge Graph", description="Active AI reasoning engine label")


class AddOnRecommendationRequest(BaseModel):
    """
    Request payload for smart merchant add-on and cross-sell recommendations.
    """
    product_id: str = Field(..., description="Base product ID being purchased (e.g. 'KB001')")
    remaining_budget: Optional[float] = Field(default=None, description="Optional customer mandate budget headroom in INR (₹)")


class AddOnRecommendationResponse(BaseModel):
    """
    Smart upsell / cross-sell response returned by the Merchant Agent.
    """
    base_product_id: str = Field(..., description="Base product ID")
    addons: List[ProductQuote] = Field(default_factory=list, description="Complementary add-on items that fit within headroom")
    merchant_pitch: str = Field(..., description="Merchant sales pitch explaining the value add")
    total_addons: int = Field(..., description="Count of recommended add-on items")
    llm_reasoning_used: bool = Field(default=False, description="Whether live LLM reasoning (Gemini/OpenAI) generated these add-ons")
    llm_engine: Optional[str] = Field(default="Dynamic Headroom & Synergy Reasoning", description="Active AI reasoning engine label")



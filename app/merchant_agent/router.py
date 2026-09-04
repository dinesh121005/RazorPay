"""
REST API router for Merchant-Side Sales AI Agent (Agent-to-Agent Commerce).
Exposes public /merchant/inquire endpoint for external Buyer AI Agents.
"""
from fastapi import APIRouter, status

from app.merchant_agent.models import (
    AddOnRecommendationRequest,
    AddOnRecommendationResponse,
    InquiryRequest,
    InquiryResponse,
)
from app.merchant_agent.service import merchant_agent_service

router = APIRouter(prefix="/merchant", tags=["merchant-agent"])


@router.post(
    "/inquire",
    response_model=InquiryResponse,
    status_code=status.HTTP_200_OK,
    summary="Agent-to-Agent (A2A) Product Procurement Inquiry",
    description="Allows a Buyer AI Agent (e.g. Claude) to query the Merchant Sales Agent with natural language requirements and receive structured product quotes."
)
@router.post(
    "/inquiry",
    response_model=InquiryResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def inquire_merchant(request: InquiryRequest) -> InquiryResponse:

    """
    Handles natural language procurement requests from Buyer AI Agents and returns ranked product quotes.
    """
    return merchant_agent_service.process_inquiry(request)


@router.post(
    "/recommend-addons",
    response_model=AddOnRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Track 01 Merchant Revenue Growth: Smart Add-Ons & Cross-Sell",
    description="Recommends complementary add-on products to grow merchant basket size under customer mandate headroom."
)
def recommend_addons_endpoint(request: AddOnRecommendationRequest) -> AddOnRecommendationResponse:
    """
    Formulates cross-sell product recommendations for an approved purchase under available budget headroom.
    """
    return merchant_agent_service.recommend_addons(
        product_id=request.product_id,
        remaining_budget=request.remaining_budget,
    )


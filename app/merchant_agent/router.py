"""
REST API router for Merchant-Side Sales AI Agent (Agent-to-Agent Commerce).
Exposes public /merchant/inquire endpoint for external Buyer AI Agents.
"""
from fastapi import APIRouter, HTTPException, status

from app.merchant_agent.models import (
    AddOnRecommendationRequest,
    AddOnRecommendationResponse,
    InquiryRequest,
    InquiryResponse,
    RecommendationRespondRequest,
    RecommendationRespondResponse,
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
        customer_id=request.customer_id or "CUST001",
    )


@router.post(
    "/recommendation/respond",
    response_model=RecommendationRespondResponse,
    status_code=status.HTTP_200_OK,
    summary="Buyer AI Decision Response (Accept or Reject Recommendation)",
    description="Records a Buyer AI Agent's terminal ACCEPT or REJECT decision for a recommendation with terminal idempotency."
)
def respond_to_recommendation_endpoint(request: RecommendationRespondRequest) -> RecommendationRespondResponse:
    """
    Processes buyer ACCEPT or REJECT response to a recommendation.
    If ACCEPTED, executes linked add-on purchase proposal using existing single-item flow.
    Enforces terminal decision idempotency.
    """
    try:
        return merchant_agent_service.respond_to_recommendation(
            recommendation_id=request.recommendation_id,
            decision=request.decision,
            customer_id=request.customer_id or "CUST001",
            primary_transaction_id=request.primary_transaction_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

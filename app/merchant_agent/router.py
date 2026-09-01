"""
REST API router for Merchant-Side Sales AI Agent (Agent-to-Agent Commerce).
Exposes public /merchant/inquire endpoint for external Buyer AI Agents.
"""
from fastapi import APIRouter, status

from app.merchant_agent.models import InquiryRequest, InquiryResponse
from app.merchant_agent.service import merchant_agent_service

router = APIRouter(prefix="/merchant", tags=["merchant-agent"])


@router.post(
    "/inquire",
    response_model=InquiryResponse,
    status_code=status.HTTP_200_OK,
    summary="Agent-to-Agent (A2A) Product Procurement Inquiry",
    description="Allows a Buyer AI Agent (e.g. Claude) to query the Merchant Sales Agent with natural language requirements and receive structured product quotes."
)
def inquire_merchant(request: InquiryRequest) -> InquiryResponse:
    """
    Handles natural language procurement requests from Buyer AI Agents and returns ranked product quotes.
    """
    return merchant_agent_service.process_inquiry(request)

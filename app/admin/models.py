"""
Data models for admin-only mandate and customer management.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CreateCustomerRequest(BaseModel):
    """
    Request payload to provision a new customer mandate and OAuth credentials.
    """
    customer_id: str = Field(..., description="Unique customer identifier (e.g. 'CUST003')")
    display_name: str = Field(default="Demo Customer", description="Human display name of the customer (e.g. 'Dinesh Kumar')")
    mandate_limit: float = Field(..., gt=0, description="Maximum amount allowed per transaction in INR (₹)")
    allowed_categories: List[str] = Field(..., description="Authorized product categories")
    allowed_merchants: List[str] = Field(..., description="Authorized merchant IDs")
    email: Optional[str] = Field(default=None, description="Optional email address of the customer")
    username: Optional[str] = Field(default=None, description="Optional username for OAuth login (defaults to customer_id)")
    password: Optional[str] = Field(default=None, description="Optional initial password for OAuth login (defaults to 'password123')")
    expires_at: Optional[datetime] = Field(default=None, description="Optional expiration timestamp in UTC")


class UpdateMandateLimitRequest(BaseModel):
    """
    Request payload to update an existing customer's transaction limit.
    """
    mandate_limit: float = Field(..., gt=0, description="New maximum transaction limit in INR (₹)")

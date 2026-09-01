"""
Data models for minimal OAuth 2.1 authorization server, customer credentials, and token grants.
"""
from typing import Optional
from pydantic import BaseModel, Field


class CustomerCredentials(BaseModel):
    """
    Stored user credentials bound to a customer_id.
    Separate from Mandate model to distinguish login credentials from spending rules.
    """
    customer_id: str = Field(..., description="Customer identifier (e.g. 'CUST001')")
    username: str = Field(..., description="Login username")
    email: str = Field(..., description="User email address")
    password_hash: str = Field(..., description="Hex string of salted PBKDF2 hash")
    salt: str = Field(..., description="Hex salt for hashing")


class AuthorizeSubmitRequest(BaseModel):
    """
    Form submission payload for /oauth/authorize.
    """
    username: str
    password: str
    client_id: str
    redirect_uri: str
    response_type: str = "code"
    state: Optional[str] = None
    scope: Optional[str] = "purchase"


class TokenRequest(BaseModel):
    """
    Token request payload for /oauth/token supporting authorization_code and refresh_token grants.
    """
    grant_type: str = Field(default="authorization_code", description="Grant type ('authorization_code' or 'refresh_token')")
    code: Optional[str] = Field(default=None, description="Authorization code for authorization_code grant")
    redirect_uri: Optional[str] = Field(default=None, description="Redirect URI must match authorization request")
    refresh_token: Optional[str] = Field(default=None, description="Refresh token for refresh_token grant")
    client_id: Optional[str] = Field(default=None, description="Pre-registered OAuth client ID")
    client_secret: Optional[str] = Field(default=None, description="Pre-registered OAuth client secret")
    scope: Optional[str] = Field(default="purchase", description="Requested scope")


class TokenResponse(BaseModel):
    """
    Standard OAuth 2.0 token response.
    """
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    scope: Optional[str] = "purchase"

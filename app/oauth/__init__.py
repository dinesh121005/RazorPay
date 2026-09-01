"""
OAuth 2.1 Minimal Authorization Server and Customer Authentication Layer.
"""
from app.oauth.router import router as oauth_router

__all__ = ["oauth_router"]

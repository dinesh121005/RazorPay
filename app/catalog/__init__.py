"""Catalog component package."""
from app.catalog.data import PRODUCTS
from app.catalog.models import Product
from app.catalog.router import router

__all__ = ["Product", "PRODUCTS", "router"]

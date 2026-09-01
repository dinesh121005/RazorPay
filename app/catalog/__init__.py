"""Catalog component package."""
from app.catalog.data import PRODUCTS
from app.catalog.models import Product
from app.catalog.router import router
from app.catalog.service import get_product, search_products

__all__ = ["Product", "PRODUCTS", "router", "get_product", "search_products"]


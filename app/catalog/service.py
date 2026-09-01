"""
Catalog service layer.

Provides shared, reusable catalog query and lookup functions used across
both the FastAPI HTTP catalog router and the Model Context Protocol (MCP) server.
"""
from typing import List, Optional

from app.catalog.data import PRODUCTS
from app.catalog.models import Product
from app.exceptions import ProductNotFoundError


def search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
) -> List[Product]:
    """
    Search and filter products from the catalog.

    Supports intelligent multi-word keyword search on product name and description,
    category filtering (case-insensitive exact match), and maximum price upper bound.
    """
    filtered_products = PRODUCTS

    if query is not None and query.strip():
        search_term = query.strip().lower()
        query_words = [w for w in search_term.split() if w]
        filtered_products = [
            p for p in filtered_products
            if (
                search_term in p.name.lower()
                or (p.description and search_term in p.description.lower())
                or all(
                    w in f"{p.name.lower()} {p.category.lower()} {(p.description or '').lower()}"
                    for w in query_words
                )
            )
        ]

    if category is not None and category.strip():
        target_category = category.strip().lower()
        filtered_products = [
            p for p in filtered_products if p.category.lower() == target_category
        ]

    if max_price is not None:
        filtered_products = [
            p for p in filtered_products if p.price <= max_price
        ]

    return filtered_products


def get_product(product_id: str) -> Product:
    """
    Retrieve a single product by its unique product ID.
    Raises ProductNotFoundError if the product is not found in the catalog.
    """
    for product in PRODUCTS:
        if product.id == product_id:
            return product

    raise ProductNotFoundError(product_id)

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.catalog.data import PRODUCTS
from app.catalog.models import Product

router = APIRouter(prefix="/products", tags=["catalog"])


@router.get("", response_model=List[Product], summary="List and filter catalog products")
def list_products(
    category: Optional[str] = Query(
        default=None,
        description="Filter products by category name (case-insensitive)"
    ),
    max_price: Optional[float] = Query(
        default=None,
        gt=0,
        description="Filter products with price less than or equal to this maximum amount in INR (₹)"
    ),
) -> List[Product]:
    """
    Retrieve products from the catalog.
    Supports optional filtering by category and maximum price.
    """
    filtered_products = PRODUCTS

    if category is not None:
        target_category = category.strip().lower()
        filtered_products = [
            p for p in filtered_products if p.category.lower() == target_category
        ]

    if max_price is not None:
        filtered_products = [
            p for p in filtered_products if p.price <= max_price
        ]

    return filtered_products


@router.get("/{id}", response_model=Product, summary="Get product details by ID")
def get_product(id: str) -> Product:
    """
    Retrieve single product details by product ID.
    Returns 404 if the product is not found in the catalog.
    """
    for product in PRODUCTS:
        if product.id == id:
            return product

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with id '{id}' not found"
    )

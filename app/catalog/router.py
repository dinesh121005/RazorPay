from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.catalog.models import Product
from app.catalog.service import get_product, search_products
from app.exceptions import ProductNotFoundError

router = APIRouter(prefix="/products", tags=["catalog"])


@router.get("", response_model=List[Product], summary="List and filter catalog products")
def list_products(
    query: Optional[str] = Query(
        default=None,
        description="Filter products by product name (case-insensitive substring)"
    ),
    category: Optional[str] = Query(
        default=None,
        description="Filter products by category name (case-insensitive exact match)"
    ),
    max_price: Optional[float] = Query(
        default=None,
        gt=0,
        description="Filter products with price less than or equal to this maximum amount in INR (₹)"
    ),
) -> List[Product]:
    """
    Retrieve products from the catalog.
    Supports optional filtering by keyword query, category, and maximum price.
    """
    return search_products(query=query, category=category, max_price=max_price)


@router.get("/{id}", response_model=Product, summary="Get product details by ID")
def get_product_endpoint(id: str) -> Product:
    """
    Retrieve single product details by product ID.
    Returns 404 if the product is not found in the catalog.
    """
    try:
        return get_product(id)
    except ProductNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


from pydantic import BaseModel, Field


class Product(BaseModel):
    """
    Product entity representation in the Catalog.
    Strictly typed for downstream consumption by AI shopping agents and the Policy Engine.
    """
    id: str = Field(..., description="Unique identifier for the product")
    name: str = Field(..., description="Name of the product")
    category: str = Field(..., description="Category to which the product belongs")
    price: float = Field(..., gt=0, description="Price of the product in INR (₹)")
    stock: int = Field(..., ge=0, description="Available inventory stock count")
    description: str = Field(..., description="Detailed description of the product")

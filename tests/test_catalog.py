import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.catalog.data import PRODUCTS

client = TestClient(app)


def test_health_check():
    """1. GET /health returns 200 with a status payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert "version" in data


def test_get_all_products():
    """2. GET /products returns the full seed list."""
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == len(PRODUCTS)
    assert len(data) >= 4

    # Verify seed fields for each item
    for item in data:
        assert "id" in item
        assert "name" in item
        assert "category" in item
        assert "price" in item
        assert "stock" in item
        assert "description" in item


def test_filter_products_by_category_and_max_price():
    """3. GET /products?category=electronics&max_price=2000 correctly excludes the deliberately over-budget product (MN001) and includes KB001."""
    # First verify we have the over-budget item in electronics
    over_budget_items = [p for p in PRODUCTS if p.category == "electronics" and p.price > 2000]
    assert len(over_budget_items) >= 1, "Seed data must have at least one product priced > ₹2,000"

    response = client.get("/products?category=electronics&max_price=2000")
    assert response.status_code == 200
    data = response.json()

    assert len(data) > 0
    returned_ids = [p["id"] for p in data]
    assert "KB001" in returned_ids
    assert "MN001" not in returned_ids

    for product in data:
        assert product["category"].lower() == "electronics"
        assert product["price"] <= 2000


def test_get_product_by_valid_id():
    """4. GET /products/{valid_id} returns the correct single product for demo IDs KB001 and MN001."""
    # Test KB001 (keyboard, under ₹2,000)
    response_kb = client.get("/products/KB001")
    assert response_kb.status_code == 200
    data_kb = response_kb.json()
    assert data_kb["id"] == "KB001"
    assert "Keyboard" in data_kb["name"]
    assert data_kb["category"] == "electronics"
    assert data_kb["price"] < 2000

    # Test MN001 (monitor, over ₹2,000)
    response_mn = client.get("/products/MN001")
    assert response_mn.status_code == 200
    data_mn = response_mn.json()
    assert data_mn["id"] == "MN001"
    assert "Monitor" in data_mn["name"]
    assert data_mn["category"] == "electronics"
    assert data_mn["price"] > 2000


def test_get_product_by_invalid_id():
    """5. GET /products/{invalid_id} returns 404 with a clear error body."""
    response = client.get("/products/non_existent_id_999")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "non_existent_id_999" in data["detail"]


def test_search_products_by_query():
    """6. GET /products?query=keyboard returns matching products by case-insensitive name."""
    response = client.get("/products?query=keyboard")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "KB001"
    assert "Keyboard" in data[0]["name"]


def test_search_products_by_query_case_insensitive():
    """7. GET /products?query=mOnItOr matches 4K monitor case-insensitively."""
    response = client.get("/products?query=mOnItOr")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "MN001"


def test_search_products_combined_filters():
    """8. GET /products?query=cotton&category=apparel&max_price=1000 matches AP001."""
    response = client.get("/products?query=cotton&category=apparel&max_price=1000")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "AP001"


def test_search_products_no_match():
    """9. GET /products?query=nonexistent returns an empty list."""
    response = client.get("/products?query=nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data == []



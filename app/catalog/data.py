from typing import List
from app.catalog.models import Product

# In-memory seed catalog data
# Fixed Demo IDs:
# - KB001: Keyboard (under ₹2,000 limit -> approved purchase in demo)
# - MN001: Monitor (over ₹2,000 limit -> rejected purchase in demo)
# - Other products follow <CATEGORY_PREFIX><NNN> convention
#
# Merchant IDs:
# - MERCH_ELEC: Electronics and general goods merchant (original 5 products)
# - MERCH_FOOD: Food and pantry merchant (FD001, FD002)
PRODUCTS: List[Product] = [
    Product(
        id="KB001",
        name="Mechanical Gaming Keyboard",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=1499.0,
        stock=20,
        description="Compact mechanical keyboard with tactile blue switches and customizable RGB backlighting."
    ),
    Product(
        id="MN001",
        name="27-inch 4K UHD Monitor",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=4999.0,
        stock=8,
        description="27-inch Ultra HD IPS display with HDR10 support, slim bezels, and 144Hz refresh rate."
    ),
    Product(
        id="HK001",
        name="Ceramic Coffee Mug (350ml)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=499.0,
        stock=50,
        description="Matte finish heat-resistant ceramic coffee mug with ergonomic handle."
    ),
    Product(
        id="HK002",
        name="Stainless Steel Water Bottle (1L)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=899.0,
        stock=30,
        description="Double-walled vacuum insulated water bottle keeping liquids cold for 24 hours."
    ),
    Product(
        id="AP001",
        name="Organic Cotton Crew T-Shirt",
        category="apparel",
        merchant_id="MERCH_ELEC",
        price=799.0,
        stock=40,
        description="Breathable 100% organic cotton crew neck t-shirt in midnight blue."
    ),
    Product(
        id="FD001",
        name="Cold-Pressed Virgin Coconut Oil (500ml)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=349.0,
        stock=60,
        description="Unrefined cold-pressed virgin coconut oil, suitable for cooking and skincare."
    ),
    Product(
        id="FD002",
        name="Organic Rolled Oats (1kg)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=299.0,
        stock=80,
        description="Whole grain certified organic rolled oats, gluten-free, high in dietary fibre."
    ),
]

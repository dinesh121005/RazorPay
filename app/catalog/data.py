from typing import List
from app.catalog.models import Product

# Comprehensive product catalog for Agentic Commerce Gateway.
#
# Anchor Demo IDs:
# - KB001: Keyboard (under ₹2,000 limit -> approved purchase in demo)
# - MN001: Monitor (over ₹2,000 limit -> rejected purchase in demo)
# - HK001, HK002: Home & kitchen baseline items
# - AP001: Apparel baseline item
# - FD001, FD002: Food baseline items
#
# Merchant IDs:
# - MERCH_ELEC: Electronics & Technology merchant
# - MERCH_FOOD: Food, Pantry & Healthy Snacks merchant
# - MERCH_HOME: Home Appliances & Kitchenware merchant

PRODUCTS: List[Product] = [
    # ══════════════════════════════════════════════════════════════════════════════
    # 1. Electronics & Tech Accessories (12 Products)
    # ══════════════════════════════════════════════════════════════════════════════
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
        id="EL001",
        name="Ergonomic Wireless Optical Mouse",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=899.0,
        stock=45,
        description="Ergonomic silent-click optical mouse with 2.4GHz wireless and Bluetooth dual-mode connectivity."
    ),
    Product(
        id="EL002",
        name="Active Noise Cancelling Wireless Headphones",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=2499.0,
        stock=15,
        description="Over-ear Bluetooth headphones with hybrid active noise cancellation and 40-hour battery life."
    ),
    Product(
        id="EL003",
        name="7-in-1 Aluminium USB-C Multiport Hub",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=1899.0,
        stock=30,
        description="Aluminium hub with 4K HDMI, 100W Power Delivery pass-through, SD card reader, and 3 USB 3.0 ports."
    ),
    Product(
        id="EL004",
        name="1080p Full HD Pro Streaming Webcam",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=1999.0,
        stock=25,
        description="High-definition 1080p 60FPS webcam with automatic light correction and dual stereo microphones."
    ),
    Product(
        id="EL005",
        name="Fast Qi Wireless Charging Pad (15W)",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=799.0,
        stock=50,
        description="Slim non-slip 15W Qi-certified wireless charging pad with foreign object detection and LED indicator."
    ),
    Product(
        id="EL006",
        name="Braided USB-C Fast Charging Cable (2m)",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=399.0,
        stock=100,
        description="Heavy-duty nylon braided 240W USB-C to USB-C charging and 480Mbps data transfer cable."
    ),
    Product(
        id="EL007",
        name="Smart Dimmable LED Desk Lamp",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=1299.0,
        stock=35,
        description="Eye-care LED desk lamp with 5 brightness levels, 3 color temperatures, and USB charging output."
    ),
    Product(
        id="EL008",
        name="Portable Waterproof Bluetooth Speaker",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=1799.0,
        stock=28,
        description="IPX7 waterproof portable speaker with 360-degree surround sound and 12-hour playtime."
    ),
    Product(
        id="EL009",
        name="65W GaN Dual Port Fast Wall Charger",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=1499.0,
        stock=40,
        description="Compact GaN fast charger with USB-C and USB-A ports supporting laptops, tablets, and phones."
    ),
    Product(
        id="EL010",
        name="Ergonomic Aluminum Laptop Cooling Stand",
        category="electronics",
        merchant_id="MERCH_ELEC",
        price=999.0,
        stock=30,
        description="Foldable ventilated aluminum stand with adjustable height angles for 10-16 inch laptops."
    ),

    # ══════════════════════════════════════════════════════════════════════════════
    # 2. Home & Kitchen Appliances (10 Products)
    # ══════════════════════════════════════════════════════════════════════════════
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
        id="HK003",
        name="Rapid Boil Electric Glass Kettle (1.8L)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=1199.0,
        stock=25,
        description="1500W rapid boil borosilicate glass kettle with auto-shutoff and blue LED illumination."
    ),
    Product(
        id="HK004",
        name="Digital Precision Kitchen Food Scale (5kg)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=649.0,
        stock=40,
        description="High-precision digital food scale with 1g graduation, tare function, and LCD display."
    ),
    Product(
        id="HK005",
        name="French Press Coffee & Tea Maker (600ml)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=999.0,
        stock=30,
        description="Heat-resistant borosilicate glass French press with 4-level stainless steel filtration."
    ),
    Product(
        id="HK006",
        name="Pre-Seasoned Cast Iron Skillet (10-inch)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=1499.0,
        stock=20,
        description="Heavy-duty pre-seasoned cast iron skillet pan offering superior heat retention for stovetop and oven."
    ),
    Product(
        id="HK007",
        name="Electric Handheld Milk Frother",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=599.0,
        stock=45,
        description="Battery-operated stainless steel whisk frother for lattes, cappuccinos, and matcha."
    ),
    Product(
        id="HK008",
        name="Digital Touch Air Fryer (4.2L)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=3999.0,
        stock=12,
        description="1400W rapid air circulation air fryer with non-stick basket and 8 one-touch cooking presets."
    ),
    Product(
        id="HK009",
        name="Stainless Steel 2-Slot Pop-Up Toaster",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=1399.0,
        stock=22,
        description="800W toaster with 6 browning control levels, defrost, reheat, and removable crumb tray."
    ),
    Product(
        id="HK010",
        name="Leak-Proof Bento Lunch Box (1.2L)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=749.0,
        stock=35,
        description="BPA-free 3-compartment microwave-safe bento box with airtight locking lid and cutlery set."
    ),

    # ══════════════════════════════════════════════════════════════════════════════
    # 3. Foods, Pantry & Healthy Snacks (24 Products)
    # ══════════════════════════════════════════════════════════════════════════════
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
    Product(
        id="FD003",
        name="Roasted California Almonds (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=399.0,
        stock=50,
        description="Premium dry-roasted crunchy almonds lightly dusted with pure sea salt."
    ),
    Product(
        id="FD004",
        name="Salted Jumbo Whole Cashews (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=449.0,
        stock=45,
        description="Slow-roasted jumbo whole cashews with a rich buttery crunch and light salt."
    ),
    Product(
        id="FD005",
        name="Peri-Peri Roasted Foxnuts Makhana (100g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=179.0,
        stock=70,
        description="Crunchy popped lotus seeds tossed in zesty peri-peri spice blend, low calorie and gluten-free."
    ),
    Product(
        id="FD006",
        name="Dark Chocolate Almond Granola Bites (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=249.0,
        stock=60,
        description="Baked clusters of rolled oats, roasted almonds, and 70% dark Belgian chocolate chunks."
    ),
    Product(
        id="FD007",
        name="Artisan Coorg Filter Coffee Powder (500g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=420.0,
        stock=40,
        description="Traditional 80:20 Arabica and Robusta coffee chicory blend roasted in the hills of Coorg."
    ),
    Product(
        id="FD008",
        name="Raw Kashmiri Organic Acacia Honey (500g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=499.0,
        stock=35,
        description="100% pure unprocessed wild acacia honey harvested from Kashmir valleys, unpasteurized."
    ),
    Product(
        id="FD009",
        name="Pure Himalayan Pink Rock Salt (1kg)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=149.0,
        stock=90,
        description="Unrefined mineral-rich coarse pink salt naturally mined from ancient Himalayan rock beds."
    ),
    Product(
        id="FD010",
        name="Multigrain Protein Energy Bars (Pack of 6)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=299.0,
        stock=55,
        description="Nutrient-dense snack bars packed with whey protein, seeds, dates, and zero added refined sugar."
    ),
    Product(
        id="FD011",
        name="Baked Ragi & Jowar Crisp Crackers (150g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=129.0,
        stock=65,
        description="Ancient millet savory snack crackers seasoned with cumin and black pepper."
    ),
    Product(
        id="FD012",
        name="Organic Raw White Chia Seeds (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=199.0,
        stock=50,
        description="Certified organic raw chia seeds rich in Omega-3 fatty acids, plant protein, and soluble fibre."
    ),
    Product(
        id="FD013",
        name="Roasted Peanuts with Pink Salt (400g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=169.0,
        stock=75,
        description="Crispy hot-air roasted peanuts seasoned with Himalayan pink rock salt."
    ),
    Product(
        id="FD014",
        name="Royal Masala Chai Spiced Tea Blend (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=299.0,
        stock=40,
        description="Assam black CTC tea infused with crushed cardamom, cinnamon, clove, ginger, and star anise."
    ),
    Product(
        id="FD015",
        name="Tangy Tomato Quinoa Crisps (100g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=139.0,
        stock=60,
        description="Popped quinoa chips seasoned with sun-ripened tangy tomato powder and Mediterranean herbs."
    ),
    Product(
        id="FD016",
        name="All-Natural Creamy Peanut Butter (500g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=349.0,
        stock=50,
        description="100% pure roasted peanuts slow-ground into a silky spread with zero palm oil or preservatives."
    ),
    Product(
        id="FD017",
        name="Alphonso Mango Preserve Fruit Spread (340g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=259.0,
        stock=30,
        description="Gourmet handcrafted preserve made with 70% real Ratnagiri Alphonso mango pulp."
    ),
    Product(
        id="FD018",
        name="Whole Leaf Darjeeling Green Tea (100g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=280.0,
        stock=45,
        description="Single-estate whole leaf first flush green tea rich in natural antioxidants."
    ),
    Product(
        id="FD019",
        name="Superfruit Dried Berry Medley (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=389.0,
        stock=35,
        description="Antioxidant-rich blend of whole dried cranberries, wild blueberries, goji berries, and black raisins."
    ),
    Product(
        id="FD020",
        name="Baked Beetroot & Sweet Potato Chips (100g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=149.0,
        stock=55,
        description="Vibrant root vegetable crisps vacuum-cooked in cold-pressed oil with a pinch of sea salt."
    ),
    Product(
        id="FD021",
        name="Raw Pumpkin & Sunflower Seed Blend (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=219.0,
        stock=45,
        description="Nutrient-dense unroasted seed mix offering zinc, magnesium, and healthy dietary fats."
    ),
    Product(
        id="FD022",
        name="Single-Origin 70% Dark Chocolate Bar (80g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=249.0,
        stock=60,
        description="Bean-to-bar artisanal dark chocolate crafted with South Indian cacao beans and organic raw cane sugar."
    ),
    Product(
        id="FD023",
        name="Organic Moringa Herbal Infusion (50 Bags)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=320.0,
        stock=30,
        description="Caffeine-free herbal wellness tea bags made from shade-dried organic moringa oleifera leaves."
    ),
    Product(
        id="FD024",
        name="Herbed Garlic Baked Pita Chips (150g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=159.0,
        stock=50,
        description="Double-baked whole wheat pita chips seasoned with roasted garlic, oregano, and olive oil."
    ),
    Product(
        id="FD025",
        name="Organic Jaggery Peanut Chikki (300g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=189.0,
        stock=65,
        description="Traditional crunchy Indian brittle made with roasted peanuts and unrefined organic jaggery."
    ),

    # ══════════════════════════════════════════════════════════════════════════════
    # 4. Apparel (1 Product)
    # ══════════════════════════════════════════════════════════════════════════════
    Product(
        id="AP001",
        name="Organic Cotton Crew T-Shirt",
        category="apparel",
        merchant_id="MERCH_ELEC",
        price=799.0,
        stock=40,
        description="Breathable 100% organic cotton crew neck t-shirt in midnight blue."
    ),
]

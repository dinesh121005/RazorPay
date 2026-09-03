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
        name="Salem Stainless Steel Water Bottle (1L)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=899.0,
        stock=30,
        description="Double-walled vacuum insulated food-grade Salem stainless steel water bottle keeping liquids cold for 24 hours."
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
        name="Pre-Seasoned Cast Iron Dosa Tawa & Skillet (10-inch)",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=1499.0,
        stock=20,
        description="Heavy-duty pre-seasoned cast iron tawa and skillet pan hand-poured by rural Tamil artisans, perfect for crispy dosas and stovetop searing."
    ),
    Product(
        id="HK007",
        name="Electric Handheld Milk Frother",
        category="home_kitchen",
        merchant_id="MERCH_ELEC",
        price=599.0,
        stock=45,
        description="Battery-operated stainless steel whisk frother for traditional frothy filter coffee and matcha."
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
    # 3. Foods, Pantry & Tamil Nadu Regional Delicacies (25 Products)
    # ══════════════════════════════════════════════════════════════════════════════
    Product(
        id="FD001",
        name="Cold-Pressed Virgin Coconut Oil (500ml)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=349.0,
        stock=60,
        description="Authentic Pollachi cold-pressed virgin coconut oil (Mara Chekku Thengai Ennai), extracted from handpicked coconuts, unrefined and nutrient-rich for cooking and wellness."
    ),
    Product(
        id="FD002",
        name="Organic Rolled Oats & Samai Millet (1kg)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=299.0,
        stock=80,
        description="Wholesome breakfast blend of certified organic rolled oats and Little Millet (Samai) sourced from Tamil Nadu organic farms, rich in dietary fibre."
    ),
    Product(
        id="FD003",
        name="Kovilpatti Special Kadalai Mittai (400g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=199.0,
        stock=50,
        description="GI-tagged authentic Kovilpatti peanut brittle made with slow-roasted groundnuts, pure organic sugarcane jaggery syrup, and crushed cardamom."
    ),
    Product(
        id="FD004",
        name="Panruti Roasted Jumbo Cashews (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=449.0,
        stock=45,
        description="Premium grade whole cashews harvested from Panruti, slow-roasted to golden perfection with a touch of crystal sea salt."
    ),
    Product(
        id="FD005",
        name="Authentic Tirunelveli Ghee Wheat Halwa (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=220.0,
        stock=70,
        description="Legendary melting wheat halwa slow-cooked with Thamirabarani river water, fermented whole wheat milk, raw sugar, and pure desi cow ghee."
    ),
    Product(
        id="FD006",
        name="Ooty Homemade Roasted Almond Dark Chocolates (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=249.0,
        stock=60,
        description="Artisanal hill-station dark chocolate handcrafted in Ooty with rich roasted Nilgiri almonds and 70% pure cocoa."
    ),
    Product(
        id="FD007",
        name="Kumbakonam Degree Filter Coffee Blend (500g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=420.0,
        stock=40,
        description="Traditional 80:20 Kaveri delta Arabica and Peaberry coffee chicory blend roasted for brewing authentic frothy South Indian degree filter coffee."
    ),
    Product(
        id="FD008",
        name="Marthandam Wild Forest Organic Honey (500g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=499.0,
        stock=35,
        description="100% pure raw unprocessed wild honey ethically harvested by tribal apiculturists in the Marthandam Western Ghats forests of Kanyakumari."
    ),
    Product(
        id="FD009",
        name="Tuticorin Sun-Dried Natural Crystal Sea Salt (1kg)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=99.0,
        stock=90,
        description="Natural unrefined mineral-rich crystal sea salt solar-evaporated and harvested from the coastal salt pans of Thoothukudi (Tuticorin)."
    ),
    Product(
        id="FD010",
        name="Traditional Sathu Maavu Millet Health Mix (500g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=299.0,
        stock=55,
        description="Time-honored Tamil Nadu porridge mix prepared with 14 sprouted millets, pulses, almonds, cashews, cardamom, and dry ginger (Sukku)."
    ),
    Product(
        id="FD011",
        name="Manapparai Crispy Garlic Butter Murukku (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=149.0,
        stock=65,
        description="GI-tagged iconic spiral murukku from Manapparai, double-fried for signature crispness and seasoned with roasted cumin, butter, and asafoetida."
    ),
    Product(
        id="FD012",
        name="Chettinad Heritage Karuppu Kavuni Black Rice (1kg)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=240.0,
        stock=50,
        description="Nutrient-dense heritage black rice from Chettinad, prized since ancient Pandya times for its anthocyanin antioxidants, high iron, and nutty aroma."
    ),
    Product(
        id="FD013",
        name="Madurai Masala Roasted Spicy Groundnuts (400g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=169.0,
        stock=75,
        description="Crunchy street-style roasted peanuts tossed with fragrant curry leaves, roasted garlic, and fiery Madurai red chilli powder."
    ),
    Product(
        id="FD014",
        name="Nilgiri Orthodox Whole Leaf Golden Black Tea (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=299.0,
        stock=40,
        description="Single-estate high-grown orthodox whole leaf black tea from the misty Blue Mountains of Nilgiris, with bright floral liquor and brisk finish."
    ),
    Product(
        id="FD015",
        name="Srivilliputhur Traditional Ghee Palkova (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=210.0,
        stock=60,
        description="GI-certified heritage milk sweet slow-simmered in heavy-bottomed brass pans with full-cream country milk and organic cane sugar in Srivilliputhur."
    ),
    Product(
        id="FD016",
        name="Erode Wood-Pressed Gingelly Sesame Oil (500ml)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=280.0,
        stock=50,
        description="Traditional Mara Chekku gingelly oil extracted from premium Erode black sesame seeds and palm jaggery, quintessential for authentic Tamil cooking."
    ),
    Product(
        id="FD017",
        name="Salem Malgova Mango Thokku Pickle (350g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=189.0,
        stock=30,
        description="Handcrafted spicy and tangy grated green mango thokku made with famed Salem mangoes, cold-pressed sesame oil, fenugreek, and mustard."
    ),
    Product(
        id="FD018",
        name="Ooty Nilgiri Whole Leaf Green Tea (100g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=250.0,
        stock=45,
        description="Delicate single-estate green tea harvested at 6,000 feet in Ooty, minimally oxidized to preserve rich catechins and smooth grassy notes."
    ),
    Product(
        id="FD019",
        name="Kodaikanal Dried Hill Plums & Figs (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=349.0,
        stock=35,
        description="Sun-dried tart hill plums and succulent sweet figs grown in Kodaikanal orchards, lightly glazed with wild forest honey."
    ),
    Product(
        id="FD020",
        name="Nagercoil Crispy Nendran Banana Chips (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=160.0,
        stock=55,
        description="Wafer-thin raw Nendran plantain slices kettle-fried in pure cold-pressed coconut oil with natural turmeric and sea salt in Nagercoil style."
    ),
    Product(
        id="FD021",
        name="Madurai Traditional Spicy Idli Milagai Podi (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=149.0,
        stock=45,
        description="Authentic South Indian Gunpowder chutney podi hand-pounded with roasted urad dal, chana dal, red chillies, white sesame seeds, and asafoetida."
    ),
    Product(
        id="FD022",
        name="Anamalai Single-Origin 70% Craft Dark Chocolate (80g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=249.0,
        stock=60,
        description="Tree-to-bar artisanal dark chocolate made from sustainable cocoa beans cultivated in the agro-forestry estates of the Anamalai Hills, Pollachi."
    ),
    Product(
        id="FD023",
        name="Madurai Organic Moringa Leaf Herbal Infusion (50 Bags)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=260.0,
        stock=30,
        description="Caffeine-free herbal wellness infusion bags made from shade-dried organic Murungai Keerai (moringa leaves) from farms around Madurai."
    ),
    Product(
        id="FD024",
        name="Karaikudi Chettinad Spicy Mixture & Seeval (200g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=159.0,
        stock=50,
        description="Authentic Chettinad savory crunch mix made with gram flour sev, boondi, fried peanuts, roasted garlic flakes, and crisp curry leaves."
    ),
    Product(
        id="FD025",
        name="Thoothukudi Authentic Cashew Macaroons (250g)",
        category="food",
        merchant_id="MERCH_FOOD",
        price=279.0,
        stock=65,
        description="Legendary coastal Tamil Nadu cone-shaped macaroons baked with slow-whipped egg whites, sugar, and finely crushed roasted cashews."
    ),

    # ══════════════════════════════════════════════════════════════════════════════
    # 4. Apparel (1 Product)
    # ══════════════════════════════════════════════════════════════════════════════
    Product(
        id="AP001",
        name="Tiruppur Organic Cotton Crew T-Shirt",
        category="apparel",
        merchant_id="MERCH_ELEC",
        price=799.0,
        stock=40,
        description="Breathable 100% organic combed cotton crew neck t-shirt crafted in Tiruppur, the textile knitwear capital of Tamil Nadu."
    ),
]

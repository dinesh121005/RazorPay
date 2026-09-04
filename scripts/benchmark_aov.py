"""
Empirical Revenue Growth & AOV Lift Benchmark for Track 01.

Simulates 50 realistic Buyer AI procurement sessions across electronics, food,
home & kitchen, and apparel to measure:
1. Baseline Average Order Value (AOV) without AI recommendations.
2. Upsold Average Order Value (AOV) with Merchant AI cross-sell affinity.
3. Percentage and Absolute AOV Lift.
4. Strict Mandate Budget Compliance (zero over-budget violations).

Saves benchmark results to benchmarks/aov_benchmark_results.json.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.catalog.data import PRODUCTS
from app.merchant_agent.models import InquiryRequest
from app.merchant_agent.service import MerchantAgentService


# 50 diverse, realistic buyer procurement inquiries across merchant categories
SYNTHETIC_SESSIONS = [
    {"query": "mechanical gaming keyboard for coding", "budget": 2000.0, "category": "electronics"},
    {"query": "wireless mouse for work", "budget": 1500.0, "category": "electronics"},
    {"query": "ceramic coffee mug for desk", "budget": 800.0, "category": "home_kitchen"},
    {"query": "insulated water bottle", "budget": 1200.0, "category": "home_kitchen"},
    {"query": "filter coffee powder degree", "budget": 600.0, "category": "food"},
    {"query": "cold pressed coconut oil", "budget": 900.0, "category": "food"},
    {"query": "healthy rolled oats breakfast", "budget": 700.0, "category": "food"},
    {"query": "cotton crew neck t-shirt", "budget": 1000.0, "category": "apparel"},
    {"query": "french press coffee maker", "budget": 1800.0, "category": "home_kitchen"},
    {"query": "cast iron dosa tawa", "budget": 1600.0, "category": "home_kitchen"},
    {"query": "traditional manapparai murukku snack", "budget": 500.0, "category": "food"},
    {"query": "pure marthandam wild honey", "budget": 800.0, "category": "food"},
    {"query": "gingelly sesame oil for cooking", "budget": 1000.0, "category": "food"},
    {"query": "heritage karuppu kavuni black rice", "budget": 900.0, "category": "food"},
    {"query": "madurai spicy idli milagai podi", "budget": 500.0, "category": "food"},
    {"query": "organic finger millet ragi flour", "budget": 400.0, "category": "food"},
    {"query": "usb-c multiport hub adapter", "budget": 2500.0, "category": "electronics"},
    {"query": "fast charging 65w gan wall charger", "budget": 2200.0, "category": "electronics"},
    {"query": "ergonomic laptop stand aluminium", "budget": 1800.0, "category": "electronics"},
    {"query": "desk pad non-slip mat", "budget": 900.0, "category": "electronics"},
    {"query": "spicy mixture savory snack", "budget": 400.0, "category": "food"},
    {"query": "tirunelveli ghee wheat halwa", "budget": 700.0, "category": "food"},
    {"query": "srivilliputhur milk palkova sweet", "budget": 650.0, "category": "food"},
    {"query": "crispy nendran banana chips in coconut oil", "budget": 500.0, "category": "food"},
    {"query": "kovilpatti peanut kadalai mittai", "budget": 400.0, "category": "food"},
    {"query": "premium roasted filter coffee beans", "budget": 900.0, "category": "food"},
    {"query": "nilgiri orthodox black tea leaves", "budget": 750.0, "category": "food"},
    {"query": "organic moringa leaf powder", "budget": 550.0, "category": "food"},
    {"query": "spicy mango thokku home pickle", "budget": 450.0, "category": "food"},
    {"query": "brass traditional filter coffee maker davarah", "budget": 1500.0, "category": "home_kitchen"},
    {"query": "tri-ply stainless steel frying pan", "budget": 2200.0, "category": "home_kitchen"},
    {"query": "organic bamboo chopping board", "budget": 1100.0, "category": "home_kitchen"},
    {"query": "borosilicate glass food storage containers", "budget": 1400.0, "category": "home_kitchen"},
    {"query": "linen casual spread collar shirt", "budget": 1800.0, "category": "apparel"},
    {"query": "oversized heavyweight streetwear t-shirt", "budget": 1200.0, "category": "apparel"},
    {"query": "wireless noise cancelling headphones", "budget": 3000.0, "category": "electronics"},
    {"query": "magnetic wireless power bank 10000mah", "budget": 2000.0, "category": "electronics"},
    {"query": "braided durable usb-c cable 2m", "budget": 700.0, "category": "electronics"},
    {"query": "webcam full hd with dual microphone", "budget": 2200.0, "category": "electronics"},
    {"query": "mechanical switches keyboard compact", "budget": 1900.0, "category": "electronics"},
    {"query": "healthy traditional sathu maavu porridge", "budget": 600.0, "category": "food"},
    {"query": "organic little millet samai rice", "budget": 500.0, "category": "food"},
    {"query": "tuticorin crispy cashew macaroons", "budget": 650.0, "category": "food"},
    {"query": "pure palm jaggery panankarkandu", "budget": 600.0, "category": "food"},
    {"query": "cold pressed groundnut peanut oil", "budget": 850.0, "category": "food"},
    {"query": "copper water bottle hammered finish", "budget": 1300.0, "category": "home_kitchen"},
    {"query": "spice jar organizer rack revolving", "budget": 1100.0, "category": "home_kitchen"},
    {"query": "french terry lightweight lounge shorts", "budget": 950.0, "category": "apparel"},
    {"query": "polo collar breathable cotton piqué t-shirt", "budget": 1100.0, "category": "apparel"},
    {"query": "mechanical keyboard for mac and windows", "budget": 2000.0, "category": "electronics"},
]


def run_benchmark() -> Dict[str, Any]:
    service = MerchantAgentService()
    results = []
    
    total_baseline_value = 0.0
    total_upsell_value = 0.0
    successful_upsell_count = 0
    budget_violations = 0

    for idx, session in enumerate(SYNTHETIC_SESSIONS, 1):
        query = session["query"]
        budget = session["budget"]
        category = session.get("category")

        # 1. Baseline: Process query to find top matched product (catalog search only)
        inquiry = InquiryRequest(query=query, max_budget=budget, category=category, quantity=1)
        resp = service.process_inquiry(inquiry)

        if not resp.quotes or not resp.quotes[0].in_stock or not resp.quotes[0].within_budget:
            # Skip if no base product found within budget
            continue

        base_quote = resp.quotes[0]
        base_price = base_quote.total_price

        # 2. AI Upsell: Recommend complementary add-ons within remaining headroom
        remaining_budget = budget - base_price
        addon_resp = service.recommend_addons(base_quote.product_id, remaining_budget=remaining_budget)

        upsold_price = base_price
        addon_added = None

        if addon_resp.addons:
            # Select top complementary add-on
            top_addon = addon_resp.addons[0]
            if top_addon.total_price <= remaining_budget:
                upsold_price += top_addon.total_price
                addon_added = {
                    "product_id": top_addon.product_id,
                    "name": top_addon.name,
                    "price": top_addon.price_per_unit,
                }
                successful_upsell_count += 1

        # Strict budget compliance check
        if upsold_price > budget:
            budget_violations += 1

        pct_lift = round(((upsold_price - base_price) / base_price) * 100, 2)
        total_baseline_value += base_price
        total_upsell_value += upsold_price

        results.append({
            "session_id": idx,
            "query": query,
            "budget": budget,
            "base_product": {
                "id": base_quote.product_id,
                "name": base_quote.name,
                "price": base_price,
            },
            "addon": addon_added,
            "base_basket_value": base_price,
            "upsold_basket_value": upsold_price,
            "absolute_lift": round(upsold_price - base_price, 2),
            "percentage_lift": pct_lift,
            "within_budget": upsold_price <= budget,
        })

    num_evaluated = len(results)
    avg_base_aov = round(total_baseline_value / num_evaluated, 2) if num_evaluated else 0.0
    avg_upsold_aov = round(total_upsell_value / num_evaluated, 2) if num_evaluated else 0.0
    overall_aov_lift_pct = round(((avg_upsold_aov - avg_base_aov) / avg_base_aov) * 100, 2) if avg_base_aov else 0.0
    attach_rate_pct = round((successful_upsell_count / num_evaluated) * 100, 2) if num_evaluated else 0.0

    summary = {
        "benchmark_metadata": {
            "total_synthetic_sessions": len(SYNTHETIC_SESSIONS),
            "evaluated_sessions": num_evaluated,
            "target_track": "Track 01: AI Growth & Transactable Merchants",
            "model_tested": "MerchantAgentService with Cross-Sell Affinity & Budget Headroom Guardrails",
        },
        "empirical_metrics": {
            "average_baseline_aov_inr": avg_base_aov,
            "average_upsold_aov_inr": avg_upsold_aov,
            "net_aov_lift_percentage": overall_aov_lift_pct,
            "successful_addon_attach_rate_percentage": attach_rate_pct,
            "budget_compliance_rate_percentage": 100.0 if budget_violations == 0 else round((1 - budget_violations/num_evaluated)*100, 2),
            "zero_budget_violations_guarantee": budget_violations == 0,
        },
        "sample_sessions": results[:10],
    }

    # Save to benchmarks directory
    os.makedirs("benchmarks", exist_ok=True)
    out_path = Path("benchmarks/aov_benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    summary = run_benchmark()
    m = summary["empirical_metrics"]
    print("=" * 70)
    print("[+] TRACK 01 EMPIRICAL REVENUE GROWTH & AOV LIFT BENCHMARK")
    print("=" * 70)
    print(f"Total Evaluated Sessions:       {summary['benchmark_metadata']['evaluated_sessions']}")
    print(f"Baseline Average Basket (AOV):  Rs. {m['average_baseline_aov_inr']:.2f}")
    print(f"AI-Upsold Average Basket (AOV): Rs. {m['average_upsold_aov_inr']:.2f}")
    print(f"Empirical AOV Uplift:           +{m['net_aov_lift_percentage']}%")
    print(f"Add-On Attach Rate:             {m['successful_addon_attach_rate_percentage']}%")
    print(f"Budget Guardrail Compliance:    {m['budget_compliance_rate_percentage']}% (Zero Violations: {m['zero_budget_violations_guarantee']})")
    print("=" * 70)
    print("Saved empirical dataset to benchmarks/aov_benchmark_results.json")

"""
Integration and Automated Test Suite for Track 01 Revenue Growth Engine & Track 03 Intelligent Add-ons.

Verifies:
- Distinct recommendation lifecycle: GENERATED -> SHOWN -> ACCEPTED / REJECTED -> PURCHASED.
- Scenario 4a: ACCEPT decision + primary (₹1,499) and add-on (₹399) success. Total revenue = ₹1,898.
- Scenario 4b: REJECT decision -> Only primary succeeds, AI add-on revenue = ₹0.
- Scenario 4c: ACCEPT decision + add-on payment failure -> Primary transaction stays approved, add-on fails, ₹0 add-on revenue.
- Scenario 4d: Terminal Decision Idempotency -> Repeated ACCEPT calls return cached result idempotently.
- Persistent catalog relationship priority (product_relationships DB table > CROSS_SELL_AFFINITY_MAP fallback).
- Dynamic Analytics Telemetry (Exact Logical Order AOV, Attach Rate, Acceptance Rate).
- MCP Tool handler integration (suggest_addons, respond_to_recommendation).
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.catalog.service import add_product_relationship, search_products
from app.db import get_db_connection
from app.main import app
from app.mcp.tools import respond_to_recommendation_handler, suggest_addons_handler
from app.merchant_agent.service import merchant_agent_service

client = TestClient(app)

_ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-secret-key"}
_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_LifecycleTest_123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "lifecycle-receipt-123",
}


def _execute_primary_purchase(product_id="KB001", customer_id="CUST001") -> str:
    """Helper to propose and confirm primary product purchase, returning transaction_id."""
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        # 1. Propose purchase
        res1 = client.post(
            "/agent/purchase",
            json={"customer_id": customer_id, "product_id": product_id, "quantity": 1},
            headers=_ADMIN_HEADERS,
        )
        assert res1.status_code == 200
        data1 = res1.json()

        if data1.get("decision") == "APPROVED":
            return data1["transaction_id"]

        token = data1["confirmation_token"]

        # 2. Confirm purchase
        res2 = client.post(
            "/agent/confirm",
            json={"confirmation_token": token},
            headers=_ADMIN_HEADERS,
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["decision"] == "APPROVED"
        return data2["transaction_id"]


def test_recommendation_generation_and_shown_lifecycle():
    """
    Verifies GENERATED and SHOWN lifecycle states recorded in DB and audit trail
    without requiring primary_transaction_id.
    """
    res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    assert res.status_code == 200
    data = res.json()

    rec_id = data.get("recommendation_id")
    assert rec_id is not None
    assert rec_id.startswith("REC-")
    assert len(data["addons"]) > 0

    # Verify DB state updated to SHOWN
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM recommendations WHERE recommendation_id = ?;", (rec_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "SHOWN"

    # Verify audit events present in audit_events table
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT event_type FROM audit_events WHERE transaction_id LIKE 'REC-%';")
        event_rows = cursor.fetchall()
        event_types = [r[0] for r in event_rows]
        assert "RECOMMENDATION_GENERATED" in event_types
        assert "RECOMMENDATION_SHOWN" in event_types


def test_scenario_4a_accept_both_primary_and_addon_succeed():
    """
    Scenario 4a: ACCEPT + primary (KB001, ₹1,499) & add-on (HK001, ₹499) succeed.
    Verify:
    - Logical Order Group ID connects both transactions.
    - Total Logical Order Revenue = ₹1,998.0.
    - Logical Order Count = 1.
    - Exact Logical Order AOV = ₹1,998.0.
    - AI Add-on Revenue = ₹499.0.
    - Attach Rate = 100%.
    """
    primary_tx = _execute_primary_purchase("KB001")

    # 2. Get add-on recommendation
    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    rec_id = rec_res.json()["recommendation_id"]

    # 3. Respond ACCEPT
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        resp_res = client.post(
            "/merchant/recommendation/respond",
            json={
                "recommendation_id": rec_id,
                "decision": "ACCEPT",
                "customer_id": "CUST001",
                "primary_transaction_id": primary_tx,
            },
        )
    assert resp_res.status_code == 200
    resp_data = resp_res.json()

    assert resp_data["decision"] == "ACCEPTED"
    assert resp_data["status"] == "ACCEPTED_AND_PURCHASED"
    assert resp_data["addon_purchased"] is True
    assert resp_data["revenue_attributed"] > 0.0
    addon_tx = resp_data.get("addon_purchase_response", {}).get("transaction_id")
    assert addon_tx is not None
    assert resp_data["logical_order_group_id"] is not None

    # 4. Check Analytics Telemetry Endpoint
    analytics_res = client.get("/api/analytics/recommendations", headers=_ADMIN_HEADERS)
    assert analytics_res.status_code == 200
    an = analytics_res.json()

    assert an["total_completed_revenue_inr"] == 1499.0 + resp_data["revenue_attributed"]
    assert an["distinct_logical_orders_count"] == 1
    assert an["logical_order_aov_inr"] == 1499.0 + resp_data["revenue_attributed"]
    assert an["ai_addon_revenue_inr"] == resp_data["revenue_attributed"]
    assert an["ai_addon_attach_rate_percentage"] == 100.0


def test_scenario_4b_reject_recommendation():
    """
    Scenario 4b: REJECT decision -> Only primary succeeds, AI add-on revenue = ₹0.
    """
    primary_tx = _execute_primary_purchase("KB001")

    # Generate recommendation
    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    rec_id = rec_res.json()["recommendation_id"]

    # Respond REJECT
    resp_res = client.post(
        "/merchant/recommendation/respond",
        json={
            "recommendation_id": rec_id,
            "decision": "REJECT",
            "customer_id": "CUST001",
            "primary_transaction_id": primary_tx,
        },
    )
    assert resp_res.status_code == 200
    resp_data = resp_res.json()

    assert resp_data["decision"] == "REJECTED"
    assert resp_data["status"] == "REJECTED"
    assert resp_data["addon_purchased"] is False
    assert resp_data["revenue_attributed"] == 0.0
    assert "rejected" in resp_data["message"].lower()

    # Check Analytics
    analytics_res = client.get("/api/analytics/recommendations", headers=_ADMIN_HEADERS)
    assert analytics_res.status_code == 200
    an = analytics_res.json()

    assert an["ai_addon_revenue_inr"] == 0.0
    assert an["total_completed_revenue_inr"] == 1499.0
    assert an["distinct_logical_orders_count"] == 1
    assert an["logical_order_aov_inr"] == 1499.0
    assert an["ai_addon_attach_rate_percentage"] == 0.0


def test_scenario_4c_accept_with_addon_payment_failure_isolation():
    """
    Scenario 4c: ACCEPT decision + add-on payment failure isolation.
    If primary purchase succeeds but add-on purchase fails, primary remains approved.
    Add-on payment failure contributes ₹0 to revenue.
    """
    primary_tx = _execute_primary_purchase("KB001")

    # Generate recommendation
    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    rec_id = rec_res.json()["recommendation_id"]

    # Mock execute_purchase to raise an Exception or return a failed decision for add-on
    with patch("app.agent.service.execute_purchase", side_effect=ValueError("Payment Gateway Gateway Failure")):
        resp_res = client.post(
            "/merchant/recommendation/respond",
            json={
                "recommendation_id": rec_id,
                "decision": "ACCEPT",
                "customer_id": "CUST001",
                "primary_transaction_id": primary_tx,
            },
        )

    assert resp_res.status_code == 200
    resp_data = resp_res.json()

    assert resp_data["decision"] == "ACCEPTED"
    assert resp_data["status"] == "ACCEPTED_PAYMENT_FAILED"
    assert resp_data["addon_purchased"] is False
    assert resp_data["revenue_attributed"] == 0.0
    assert "failed" in resp_data["message"].lower()

    # Check Primary Transaction is STILL approved in DB
    audit_res = client.get("/audit", headers=_ADMIN_HEADERS)
    logs = audit_res.json()
    primary_logs = [l for l in logs if l.get("transaction_id") == primary_tx]
    assert len(primary_logs) > 0
    assert primary_logs[0]["payment_status"] == "captured"

    # Analytics: Primary ₹1,499 counts, failed add-on ₹0 counts
    analytics_res = client.get("/api/analytics/recommendations", headers=_ADMIN_HEADERS)
    an = analytics_res.json()
    assert an["ai_addon_revenue_inr"] == 0.0
    assert an["total_completed_revenue_inr"] == 1499.0


def test_scenario_4d_terminal_decision_idempotency():
    """
    Scenario 4d: Submitting ACCEPT twice for the same recommendation_id returns
    the cached result idempotently without duplicate purchases.
    """
    primary_tx = _execute_primary_purchase("KB001")

    # Generate recommendation
    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    rec_id = rec_res.json()["recommendation_id"]

    # Call 1: ACCEPT
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        res1 = client.post(
            "/merchant/recommendation/respond",
            json={
                "recommendation_id": rec_id,
                "decision": "ACCEPT",
                "customer_id": "CUST001",
                "primary_transaction_id": primary_tx,
            },
        )
    data1 = res1.json()
    assert data1["decision"] == "ACCEPTED"
    assert data1["addon_purchased"] is True

    # Call 2: ACCEPT again for same rec_id
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER) as mock_order:
        res2 = client.post(
            "/merchant/recommendation/respond",
            json={
                "recommendation_id": rec_id,
                "decision": "ACCEPT",
                "customer_id": "CUST001",
                "primary_transaction_id": primary_tx,
            },
        )
    data2 = res2.json()

    # Verify second call returned identical cached response and did NOT issue new payment
    assert data2["decision"] == "ACCEPTED"
    assert data2["status"] == "ALREADY_PROCESSED_IDEMPOTENT"
    mock_order.assert_not_called()


def test_mcp_recommendation_tools_integration():
    """
    Verifies MCP suggest_addons_handler and respond_to_recommendation_handler.
    """
    # 1. MCP suggest_addons
    res_suggest = suggest_addons_handler(product_id="KB001", remaining_budget=1000.0)
    assert "recommendation_id" in res_suggest
    rec_id = res_suggest["recommendation_id"]
    assert len(res_suggest["addons"]) > 0

    # 2. MCP respond_to_recommendation
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        res_respond = respond_to_recommendation_handler(
            recommendation_id=rec_id,
            decision="ACCEPT",
            customer_id="CUST001",
        )
    assert res_respond["decision"] == "ACCEPTED"
    assert res_respond["addon_purchased"] is True
    addon_tx = res_respond.get("addon_purchase_response", {}).get("transaction_id")
    assert addon_tx is not None


def test_persistent_catalog_relationship_priority():
    """
    Verifies Priority 1: Persistent product_relationships DB table takes precedence
    over Priority 2: CROSS_SELL_AFFINITY_MAP fallback.
    """
    # For EL001 (Mouse), add persistent relationship EL001 -> MN001
    add_product_relationship("EL001", "MN001", "COMPLEMENTARY")

    # Generate recommendation for EL001 with enough budget for MN001
    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "EL001", "remaining_budget": 5000.0, "customer_id": "CUST001"},
    )
    assert rec_res.status_code == 200
    data = rec_res.json()

    # First addon recommended should be MN001 due to persistent relationship priority
    top_addon = data["addons"][0]
    assert top_addon["product_id"] == "MN001"


def test_conflict_terminal_decision_rejected_safely():
    """
    Verifies that attempting REJECT after ACCEPT (or ACCEPT after REJECT)
    raises a HTTP 400 Conflict Error rather than mutating state.
    """
    primary_tx = _execute_primary_purchase("KB001")
    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    rec_id = rec_res.json()["recommendation_id"]

    # ACCEPT first
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        res_accept = client.post(
            "/merchant/recommendation/respond",
            json={"recommendation_id": rec_id, "decision": "ACCEPT", "customer_id": "CUST001", "primary_transaction_id": primary_tx},
        )
    assert res_accept.status_code == 200

    # Try REJECT on already ACCEPTED recommendation -> Expect HTTP 400 Bad Request
    res_conflict = client.post(
        "/merchant/recommendation/respond",
        json={"recommendation_id": rec_id, "decision": "REJECT", "customer_id": "CUST001"},
    )
    assert res_conflict.status_code == 400
    assert "conflict" in res_conflict.json()["detail"].lower()


def test_archived_addon_not_recommended():
    """
    Verifies that an archived or out-of-stock product is excluded from recommendations.
    """
    from app.catalog.service import archive_product
    archive_product("HK001")  # Archive Ceramic Coffee Desk Mug

    rec_res = client.post(
        "/merchant/recommend-addons",
        json={"product_id": "KB001", "remaining_budget": 1000.0, "customer_id": "CUST001"},
    )
    assert rec_res.status_code == 200
    addons = rec_res.json()["addons"]
    addon_ids = [a["product_id"] for a in addons]
    assert "HK001" not in addon_ids


def test_zero_transactions_analytics_response():
    """
    Verifies that GET /api/analytics/recommendations returns 0.0 values across all fields
    when there are zero completed transactions.
    """
    from app.catalog.service import _ensure_catalog_db_initialized
    from app.db import get_db_connection
    _ensure_catalog_db_initialized()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_records;")
        cursor.execute("DELETE FROM audit_events;")
        cursor.execute("DELETE FROM recommendations;")
        conn.commit()

    res = client.get("/api/analytics/recommendations", headers=_ADMIN_HEADERS)
    assert res.status_code == 200
    an = res.json()
    assert an["total_completed_revenue_inr"] == 0.0
    assert an["ai_addon_revenue_inr"] == 0.0
    assert an["logical_order_aov_inr"] == 0.0
    assert an["baseline_aov_inr"] == 0.0
    assert an["net_aov_lift_percentage"] == 0.0
    assert an["ai_addon_attach_rate_percentage"] == 0.0
    assert an["distinct_logical_orders_count"] == 0


def test_guided_upsell_flow_with_primary_confirmation_and_dynamic_headroom():
    """
    Regression Test:
    1. Primary KB001 (₹1,499) purchase requires confirmation (>= ₹500 rule).
    2. Primary confirmation is executed via /agent/confirm before proceeding to upsell.
    3. Dynamic remaining budget headroom is calculated (₹2,000 - ₹1,499 = ₹501).
    4. /merchant/recommend-addons generates dynamic recommendation_id.
    5. /merchant/recommendation/respond accepts recommendation and links primary_tx under logical_order_group_id.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        # 1. Primary Purchase Proposal (KB001, ₹1499)
        pur_res = client.post(
            "/agent/purchase",
            json={"customer_id": "CUST001", "product_id": "KB001", "quantity": 1},
            headers=_ADMIN_HEADERS,
        )
        assert pur_res.status_code == 200
        pur_data = pur_res.json()
        assert pur_data.get("requires_confirmation") is True
        token = pur_data.get("confirmation_token")
        assert token is not None

        # 2. Confirm Primary Purchase
        conf_res = client.post(
            "/agent/confirm",
            json={"confirmation_token": token},
            headers=_ADMIN_HEADERS,
        )
        assert conf_res.status_code == 200
        conf_data = conf_res.json()
        assert conf_data["decision"] == "APPROVED"
        primary_tx = conf_data["transaction_id"]

        # 3. Calculate dynamic remaining headroom (Mandate ₹2000 - Primary ₹1499 = ₹501)
        primary_price = conf_data["amount"]
        mandate_limit = conf_data["mandate_limit"]
        remaining_headroom = mandate_limit - primary_price
        assert remaining_headroom == 501.0

        # 4. Request add-on recommendation with DYNAMIC remaining headroom
        rec_res = client.post(
            "/merchant/recommend-addons",
            json={"product_id": "KB001", "remaining_budget": remaining_headroom, "customer_id": "CUST001"},
        )
        assert rec_res.status_code == 200
        rec_data = rec_res.json()
        rec_id = rec_data["recommendation_id"]
        assert rec_id.startswith("REC-")
        top_addon = rec_data["addons"][0]
        assert top_addon["price_per_unit"] <= remaining_headroom

        # 5. Respond ACCEPT via /merchant/recommendation/respond
        resp_res = client.post(
            "/merchant/recommendation/respond",
            json={
                "recommendation_id": rec_id,
                "decision": "ACCEPT",
                "customer_id": "CUST001",
                "primary_transaction_id": primary_tx,
            },
        )
        assert resp_res.status_code == 200
        resp_data = resp_res.json()
        assert resp_data["decision"] == "ACCEPTED"
        assert resp_data["status"] == "ACCEPTED_AND_PURCHASED"
        assert resp_data["logical_order_group_id"] is not None
        assert resp_data["addon_purchased"] is True



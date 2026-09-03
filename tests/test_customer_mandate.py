"""
Tests for Conversational Customer Sovereign Mandate Management & MCP Tools.
Ensures that the AI Buyer can help the user inspect and modify their spending limits
directly within the conversation with Zero-Trust two-step human confirmation,
without needing a separate customer frontend or allowing merchant admins to override limits.
"""
import pytest
from app.mcp.tools import (
    authenticated_customer_id,
    get_spending_mandate_handler,
    modify_spending_mandate_handler,
    get_spending_mandate_remote_handler,
    modify_spending_mandate_remote_handler,
)
from app.policy.store import mandate_store
from app.audit import audit_store


def test_get_spending_mandate_conversational():
    """Verify that the AI Buyer can inspect current mandate bounds in conversation."""
    res = get_spending_mandate_handler(customer_id="CUST001")
    assert res["mandate_found"] is True
    assert res["customer_id"] == "CUST001"
    assert res["max_limit_per_transaction"] > 0
    assert "electronics" in res["allowed_categories"]
    assert "spending mandate allows" in res["message"].lower()


def test_modify_spending_mandate_two_step_human_gating():
    """
    Verify strict conversational Zero-Trust gating:
    Step 1: AI Buyer requests update without token -> gateway returns confirmation challenge.
    Step 2: User confirms in chat -> AI Buyer calls with token -> gateway updates limit.
    """
    # Step 1: Initial request without confirmation token
    step1 = modify_spending_mandate_handler(
        new_limit=3500.0,
        confirmation_token=None,
        customer_id="CUST001",
    )
    assert step1["requires_confirmation"] is True
    assert step1["status"] == "AWAITING_HUMAN_CONFIRMATION"
    assert step1["proposed_limit"] == 3500.0
    assert "confirmation_token" in step1
    token = step1["confirmation_token"]
    assert "Do you authorize this change?" in step1["human_prompt"]

    # Limit has NOT changed yet
    mandate_before = mandate_store.get_mandate("CUST001")
    assert mandate_before.max_transaction_amount != 3500.0

    # Step 2: Human authorizes in conversation -> execute with token
    step2 = modify_spending_mandate_handler(
        new_limit=3500.0,
        confirmation_token=token,
        customer_id="CUST001",
    )
    assert step2["success"] is True
    assert step2["status"] == "APPROVED_AND_UPDATED"
    assert step2["new_limit"] == 3500.0

    # Mandate is now officially updated in store
    mandate_after = mandate_store.get_mandate("CUST001")
    assert mandate_after.max_transaction_amount == 3500.0


def test_modify_spending_mandate_tampered_or_invalid_token():
    """Verify forged or tampered confirmation tokens are rejected."""
    res = modify_spending_mandate_handler(
        new_limit=5000.0,
        confirmation_token="invalid.fake.jwt.token",
        customer_id="CUST001",
    )
    assert res["success"] is False
    assert "Invalid or expired confirmation token" in res["error"]


def test_modify_spending_mandate_bounds_enforcement():
    """Verify safety bounds: minimum ₹100, maximum ₹50,000."""
    # Below ₹100
    r_low = modify_spending_mandate_handler(
        new_limit=50.0,
        customer_id="CUST001",
    )
    assert r_low["success"] is False
    assert "Minimum spending mandate limit" in r_low["error"]

    # Above ₹50,000 safety threshold
    r_high = modify_spending_mandate_handler(
        new_limit=75000.0,
        customer_id="CUST001",
    )
    assert r_high["success"] is False
    assert "Maximum allowable" in r_high["error"]


def test_remote_mcp_mandate_bound_to_authenticated_customer():
    """Verify remote MCP handlers automatically bind to verified OAuth JWT customer."""
    token = authenticated_customer_id.set("CUST002")
    try:
        # Check mandate for CUST002
        res = get_spending_mandate_remote_handler()
        assert res["customer_id"] == "CUST002"

        # Request update for CUST002
        step1 = modify_spending_mandate_remote_handler(new_limit=4000.0)
        assert step1["requires_confirmation"] is True
        assert step1["customer_id"] == "CUST002"

        # Confirm update for CUST002
        step2 = modify_spending_mandate_remote_handler(
            new_limit=4000.0,
            confirmation_token=step1["confirmation_token"],
        )
        assert step2["success"] is True
        assert step2["customer_id"] == "CUST002"
        assert step2["new_limit"] == 4000.0
    finally:
        authenticated_customer_id.reset(token)

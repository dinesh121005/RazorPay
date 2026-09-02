from datetime import datetime, timedelta, timezone
import pytest
from app.policy.engine import evaluate
from app.policy.mandate import Mandate
from app.policy.requests import PolicyDecision, PurchaseRequest, RuleViolated
from app.policy.store import DEMO_MANDATES, MandateStore, mandate_store


@pytest.fixture
def demo_mandate() -> Mandate:
    return DEMO_MANDATES["CUST001"].model_copy()


# ==========================================
# 1. Canonical Demo Cases
# ==========================================

def test_canonical_demo_kb001_approved(demo_mandate):
    """Canonical demo case 1: CUST001 buying KB001 at seeded price (₹1,499.00) -> APPROVED."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "APPROVED"
    assert decision.rule_violated is None
    assert "within mandate limit" in decision.reason
    assert "1499.00" in decision.reason
    assert "2000.00" in decision.reason


def test_canonical_demo_mn001_rejected_over_limit(demo_mandate):
    """Canonical demo case 2: CUST001 buying MN001 at seeded price (₹4,999.00) -> REJECTED (AMOUNT_EXCEEDS_LIMIT)."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="MN001",
        category="electronics",
        amount=4999.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.AMOUNT_EXCEEDS_LIMIT
    assert "exceeds maximum mandate limit" in decision.reason
    assert "4999.00" in decision.reason
    assert "2000.00" in decision.reason


# ==========================================
# 2. Isolated Rule Violations
# ==========================================

def test_isolated_violation_customer_mismatch(demo_mandate):
    """Isolated rule 1 violation: Customer ID mismatch -> CUSTOMER_MISMATCH."""
    req = PurchaseRequest(
        customer_id="CUST_OTHER",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.CUSTOMER_MISMATCH
    assert "CUST_OTHER" in decision.reason
    assert "CUST001" in decision.reason


def test_isolated_violation_mandate_expired():
    """Isolated rule 2 violation: Expired mandate -> MANDATE_EXPIRED."""
    expired_mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        currency="INR",
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, expired_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.MANDATE_EXPIRED
    assert "expired" in decision.reason.lower()


def test_isolated_violation_merchant_not_allowed(demo_mandate):
    """Isolated rule 3 violation: Unauthorized merchant -> MERCHANT_NOT_ALLOWED."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="UNAUTHORIZED_STORE",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.MERCHANT_NOT_ALLOWED
    assert "UNAUTHORIZED_STORE" in decision.reason


def test_isolated_violation_category_not_allowed(demo_mandate):
    """Isolated rule 4 violation: Unauthorized category -> CATEGORY_NOT_ALLOWED."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="AUTO001",
        category="automotive",
        amount=500.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.CATEGORY_NOT_ALLOWED
    assert "automotive" in decision.reason


def test_isolated_violation_amount_exceeds_limit(demo_mandate):
    """Isolated rule 5 violation: Amount exceeding mandate limit -> AMOUNT_EXCEEDS_LIMIT."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=2500.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.AMOUNT_EXCEEDS_LIMIT
    assert "2500.00" in decision.reason


# ==========================================
# 3. Exact Boundary Cases
# ==========================================

def test_boundary_exact_max_amount_approved(demo_mandate):
    """Boundary test: Amount exactly equal to ₹2,000.00 is APPROVED."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="SPEC001",
        category="electronics",
        amount=2000.00,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "APPROVED"
    assert decision.rule_violated is None
    assert "within mandate limit" in decision.reason


def test_boundary_amount_over_by_one_paisa_rejected(demo_mandate):
    """Boundary test: Amount of ₹2,000.01 (over by ₹0.01) is REJECTED."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="SPEC002",
        category="electronics",
        amount=2000.01,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, demo_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.AMOUNT_EXCEEDS_LIMIT
    assert "2000.01" in decision.reason


# ==========================================
# 4. Expiry Handling Cases
# ==========================================

def test_expiry_future_expires_at_approved():
    """Expiry test: Mandate with future expires_at is APPROVED."""
    future_mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        currency="INR",
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, future_mandate)

    assert decision.status == "APPROVED"
    assert decision.rule_violated is None


def test_expiry_past_expires_at_rejected():
    """Expiry test: Mandate with past expires_at is REJECTED (MANDATE_EXPIRED)."""
    past_mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        currency="INR",
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req, past_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.MANDATE_EXPIRED


# ==========================================
# 5. Rule Ordering / Fail-Fast Priority Case
# ==========================================

def test_rule_ordering_first_violation_wins():
    """
    Rule ordering test: When multiple violations exist simultaneously
    (e.g., wrong customer, expired mandate, unauthorized merchant, unauthorized category, over amount),
    the first check (CUSTOMER_MISMATCH) must be returned.
    """
    expired_mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        currency="INR",
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    # Violates customer_id, merchant, category, and amount all at once
    req = PurchaseRequest(
        customer_id="CUST_INVALID",
        product_id="BAD001",
        category="luxury",
        amount=99999.0,
        merchant="ILLEGAL_MERCHANT",
        quantity=1
    )
    decision = evaluate(req, expired_mandate)

    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.CUSTOMER_MISMATCH


# ==========================================
# 6. Case-Insensitivity & Whitespace Tolerance
# ==========================================

def test_merchant_case_and_whitespace_tolerance(demo_mandate):
    """Merchant check is case-insensitive and trims leading/trailing whitespace."""
    req_uppercase = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="  merch_elec  ",
        quantity=1
    )
    decision = evaluate(req_uppercase, demo_mandate)
    assert decision.status == "APPROVED"
    assert decision.rule_violated is None


def test_category_case_and_whitespace_tolerance(demo_mandate):
    """Category check is case-insensitive and trims leading/trailing whitespace."""
    req_mixed_case = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="  Electronics  ",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision = evaluate(req_mixed_case, demo_mandate)
    assert decision.status == "APPROVED"
    assert decision.rule_violated is None


# ==========================================
# 7. Function Purity Cases
# ==========================================

def test_evaluate_purity_repeatable_output(demo_mandate):
    """Calling evaluate() multiple times with identical arguments returns identical PolicyDecisions."""
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    decision1 = evaluate(req, demo_mandate)
    decision2 = evaluate(req, demo_mandate)

    assert decision1 == decision2


def test_evaluate_purity_no_mandate_mutation(demo_mandate):
    """Calling evaluate() does not mutate any fields of the input Mandate object."""
    original_dict = demo_mandate.model_dump()
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1
    )
    evaluate(req, demo_mandate)
    after_dict = demo_mandate.model_dump()

    assert original_dict == after_dict


# ==========================================
# 8. MandateStore Cases
# ==========================================

def test_mandate_store_known_customer():
    """MandateStore returns valid mandate for known customer CUST001."""
    store = MandateStore()
    mandate = store.get_mandate("CUST001")
    assert mandate is not None
    assert mandate.customer_id == "CUST001"
    assert mandate.max_transaction_amount == 2000.0


def test_mandate_store_unknown_customer():
    """MandateStore returns None for unknown customer."""
    store = MandateStore()
    mandate = store.get_mandate("UNKNOWN_CUST_999")
    assert mandate is None


def test_mandate_store_seeded_from_demo_mandates():
    """MandateStore seeded instance matches DEMO_MANDATES['CUST001']."""
    store = MandateStore()
    stored_mandate = store.get_mandate("CUST001")
    expected_mandate = DEMO_MANDATES["CUST001"]

    assert stored_mandate == expected_mandate


# ==========================================
# 9. Mandate Expiration Boundary Tests (L4)
# ==========================================

def test_mandate_is_expired_none():
    """Mandate with expires_at=None is never expired."""
    mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=None,
    )
    assert mandate.is_expired() is False


def test_mandate_is_expired_exact_boundary():
    """
    At exact boundary (now == expires_at), mandate is still valid (not expired).
    Only now > expires_at is considered expired.
    """
    fixed_time = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=fixed_time,
    )

    # 1 second before -> False
    assert mandate.is_expired(now=fixed_time - timedelta(seconds=1)) is False

    # Exact time -> False (inclusive boundary)
    assert mandate.is_expired(now=fixed_time) is False

    # 1 second after -> True (expired)
    assert mandate.is_expired(now=fixed_time + timedelta(seconds=1)) is True


def test_mandate_is_expired_naive_datetime_handling():
    """Naive datetimes are treated as UTC without raising TypeError."""
    naive_expiry = datetime(2026, 9, 1, 12, 0, 0)
    mandate = Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        allowed_categories=["electronics"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=naive_expiry,
    )

    naive_now_before = datetime(2026, 9, 1, 11, 0, 0)
    naive_now_after = datetime(2026, 9, 1, 13, 0, 0)

    assert mandate.is_expired(now=naive_now_before) is False
    assert mandate.is_expired(now=naive_now_after) is True


def test_mandate_store_save_mandate():
    """MandateStore.save_mandate correctly stores a mandate."""
    store = MandateStore()
    custom_mandate = Mandate(
        customer_id="CUST_CUSTOM",
        max_transaction_amount=3000.0,
        allowed_categories=["apparel"],
        allowed_merchants=["MERCH_ELEC"],
    )
    store.save_mandate(custom_mandate)
    retrieved = store.get_mandate("CUST_CUSTOM")
    assert retrieved is not None
    assert retrieved.customer_id == "CUST_CUSTOM"
    assert retrieved.max_transaction_amount == 3000.0


def test_policy_engine_daily_limit_approved_within_bounds(demo_mandate):
    """Cumulative daily spend + current amount <= daily_limit -> APPROVED."""
    demo_mandate.daily_limit = 5000.0
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1,
    )
    # Already spent 2000.0 today: 2000 + 1499 = 3499 <= 5000 -> APPROVED
    decision = evaluate(req, demo_mandate, current_daily_spend=2000.0)
    assert decision.status == "APPROVED"
    assert decision.rule_violated is None


def test_policy_engine_daily_limit_rejected_exceeded(demo_mandate):
    """Cumulative daily spend + current amount > daily_limit -> REJECTED (DAILY_LIMIT_EXCEEDED)."""
    demo_mandate.daily_limit = 3000.0
    req = PurchaseRequest(
        customer_id="CUST001",
        product_id="KB001",
        category="electronics",
        amount=1499.0,
        merchant="MERCH_ELEC",
        quantity=1,
    )
    # Already spent 2000.0 today: 2000 + 1499 = 3499 > 3000 -> REJECTED
    decision = evaluate(req, demo_mandate, current_daily_spend=2000.0)
    assert decision.status == "REJECTED"
    assert decision.rule_violated == RuleViolated.DAILY_LIMIT_EXCEEDED
    assert "daily mandate cap" in decision.reason




"""
Tests for Phase 6 — SQLite Audit Trail.

Covers:
1. Unit tests for AuditStore (table creation, two-phase writes, listing with filters, get).
2. End-to-end integration tests via TestClient (purchase flow -> audit record verification).
3. Query and filter tests on GET /audit.
4. 404 behavior on GET /audit/{transaction_id}.
5. Terminal state verification (approved with payment, rejected with NULL payment, payment failed).
"""
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.audit import AuditRecord, AuditStore, audit_store
from app.main import app

client = TestClient(app)

_CREATE_ORDER = "app.payment.razorpay_client.create_order"
_FAKE_ORDER = {
    "id": "order_AuditTest_ABC123",
    "entity": "order",
    "amount": 149900,
    "currency": "INR",
    "status": "created",
    "receipt": "some-audit-txn-id",
}


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """
    Ensure all tests run against a clean, isolated SQLite database file
    and never pollute or depend on the production gateway.db file.
    """
    test_db = str(tmp_path / "test_gateway.db")
    monkeypatch.setattr(audit_store, "db_path", test_db)
    audit_store._init_db()
    yield test_db


# ══════════════════════════════════════════════════════════════════════════════
# 1. AuditStore Unit Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_audit_store_write_proposal_phase_a(tmp_path):
    """
    Phase A: write_proposal creates an audit record with NULL payment fields.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_a.db"))
    txn_id = "txn-unit-001"

    store.write_proposal(
        transaction_id=txn_id,
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Transaction amount ₹1499.00 is within mandate limit of ₹2000.00.",
    )

    record = store.get(txn_id)
    assert record is not None
    assert record.transaction_id == txn_id
    assert record.customer_id == "CUST001"
    assert record.product_id == "KB001"
    assert record.merchant_id == "MERCH_ELEC"
    assert record.quantity == 1
    assert record.amount == 1499.0
    assert record.decision == "APPROVED"
    assert "within mandate limit" in record.decision_reason
    assert record.payment_status is None
    assert record.razorpay_order_id is None
    assert record.timestamp is not None


def test_audit_store_update_payment_outcome_phase_b(tmp_path):
    """
    Phase B: update_payment_outcome updates the existing row with payment status & order ID.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_b.db"))
    txn_id = "txn-unit-002"

    store.write_proposal(
        transaction_id=txn_id,
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Transaction amount within limit.",
    )

    store.update_payment_outcome(
        transaction_id=txn_id,
        payment_status="created",
        razorpay_order_id="order_Razorpay_XYZ999",
    )

    record = store.get(txn_id)
    assert record is not None
    assert record.decision == "APPROVED"
    assert record.payment_status == "created"
    assert record.razorpay_order_id == "order_Razorpay_XYZ999"


def test_audit_store_update_payment_failure(tmp_path):
    """
    Phase B on payment failure: records payment_status='failed' and razorpay_order_id=None.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_c.db"))
    txn_id = "txn-unit-003"

    store.write_proposal(
        transaction_id=txn_id,
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Transaction amount within limit.",
    )

    store.update_payment_outcome(
        transaction_id=txn_id,
        payment_status="failed",
        razorpay_order_id=None,
    )

    record = store.get(txn_id)
    assert record is not None
    assert record.decision == "APPROVED"
    assert record.payment_status == "failed"
    assert record.razorpay_order_id is None


def test_audit_store_list_and_filters(tmp_path):
    """
    Verifies AuditStore.list() returns records in reverse chronological order
    and correctly filters by customer_id and decision.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_list.db"))

    store.write_proposal(
        transaction_id="txn-1",
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Approved reason",
        timestamp="2026-08-30T10:00:00Z",
    )
    store.write_proposal(
        transaction_id="txn-2",
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4999.0,
        decision="REJECTED",
        decision_reason="Exceeds limit",
        timestamp="2026-08-30T11:00:00Z",
    )
    store.write_proposal(
        transaction_id="txn-3",
        customer_id="CUST002",
        product_id="FD001",
        merchant_id="MERCH_FOOD",
        quantity=1,
        amount=349.0,
        decision="REJECTED",
        decision_reason="Merchant not allowed",
        timestamp="2026-08-30T12:00:00Z",
    )

    # All records (newest first: txn-3, txn-2, txn-1)
    all_records = store.list()
    assert len(all_records) == 3
    assert [r.transaction_id for r in all_records] == ["txn-3", "txn-2", "txn-1"]

    # Filter by customer_id
    cust1_records = store.list(customer_id="CUST001")
    assert len(cust1_records) == 2
    assert [r.transaction_id for r in cust1_records] == ["txn-2", "txn-1"]

    # Filter by decision
    rejected_records = store.list(decision="REJECTED")
    assert len(rejected_records) == 2
    assert [r.transaction_id for r in rejected_records] == ["txn-3", "txn-2"]

    approved_records = store.list(decision="APPROVED")
    assert len(approved_records) == 1
    assert approved_records[0].transaction_id == "txn-1"

    # Filter by customer_id and decision
    cust1_rejected = store.list(customer_id="CUST001", decision="REJECTED")
    assert len(cust1_rejected) == 1
    assert cust1_rejected[0].transaction_id == "txn-2"


def test_audit_store_get_not_found(tmp_path):
    """
    AuditStore.get returns None for non-existent transaction_id.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_none.db"))
    assert store.get("non-existent-id") is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. End-to-End Integration Tests via TestClient
# ══════════════════════════════════════════════════════════════════════════════

def test_purchase_approved_creates_complete_audit_record():
    """
    Canonical Approved Case: CUST001 + KB001 (₹1,499 <= ₹2,000)
    1. POST /agent/purchase -> returns 200 APPROVED + payment status 'created'.
    2. GET /audit/{transaction_id} -> returns audit row with decision='APPROVED',
       payment_status='created', razorpay_order_id matching response.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

    assert response.status_code == 200
    resp_data = response.json()
    txn_id = resp_data["transaction_id"]
    assert resp_data["decision"] == "APPROVED"
    assert resp_data["payment"]["status"] == "created"
    expected_order_id = resp_data["payment"]["razorpay_order_id"]

    # Verify audit record via API
    audit_resp = client.get(f"/audit/{txn_id}")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()

    assert audit_data["transaction_id"] == txn_id
    assert audit_data["customer_id"] == "CUST001"
    assert audit_data["product_id"] == "KB001"
    assert audit_data["merchant_id"] == "MERCH_ELEC"
    assert audit_data["quantity"] == 1
    assert audit_data["amount"] == 1499.0
    assert audit_data["decision"] == "APPROVED"
    assert "within mandate limit" in audit_data["decision_reason"]
    assert audit_data["payment_status"] == "created"
    assert audit_data["razorpay_order_id"] == expected_order_id
    assert audit_data["timestamp"] is not None


def test_purchase_rejected_creates_terminal_audit_record():
    """
    Canonical Rejected Case: CUST001 + MN001 (₹4,999 > ₹2,000)
    1. POST /agent/purchase -> returns 200 REJECTED, payment is None.
    2. GET /audit/{transaction_id} -> returns audit row with decision='REJECTED',
       payment_status=None, razorpay_order_id=None.
    """
    with patch(_CREATE_ORDER) as mock_create:
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "MN001",
            "quantity": 1,
        })
        mock_create.assert_not_called()

    assert response.status_code == 200
    resp_data = response.json()
    txn_id = resp_data["transaction_id"]
    assert resp_data["decision"] == "REJECTED"

    # Verify audit record
    audit_resp = client.get(f"/audit/{txn_id}")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()

    assert audit_data["transaction_id"] == txn_id
    assert audit_data["customer_id"] == "CUST001"
    assert audit_data["product_id"] == "MN001"
    assert audit_data["merchant_id"] == "MERCH_ELEC"
    assert audit_data["quantity"] == 1
    assert audit_data["amount"] == 4999.0
    assert audit_data["decision"] == "REJECTED"
    assert "exceeds maximum mandate limit" in audit_data["decision_reason"]
    assert audit_data["payment_status"] is None
    assert audit_data["razorpay_order_id"] is None


def test_purchase_payment_failure_recorded_in_audit():
    """
    Payment Failure Case: Approved by policy, but Razorpay SDK raises exception.
    Audit row records decision='APPROVED' with payment_status='failed'.
    """
    with patch(_CREATE_ORDER, side_effect=RuntimeError("SDK timeout")):
        response = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })

    assert response.status_code == 200
    resp_data = response.json()
    txn_id = resp_data["transaction_id"]
    assert resp_data["decision"] == "APPROVED"
    assert resp_data["payment"]["status"] == "failed"

    # Verify audit record reflects payment failure
    audit_resp = client.get(f"/audit/{txn_id}")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()

    assert audit_data["transaction_id"] == txn_id
    assert audit_data["decision"] == "APPROVED"
    assert audit_data["payment_status"] == "failed"
    assert audit_data["razorpay_order_id"] is None


def test_get_audit_endpoints_and_filtering():
    """
    Verify GET /audit lists records and properly applies query filters.
    """
    # 1. Seed three transactions
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        resp1 = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "KB001",
            "quantity": 1,
        })
    with patch(_CREATE_ORDER):
        resp2 = client.post("/agent/purchase", json={
            "customer_id": "CUST001",
            "product_id": "MN001",
            "quantity": 1,
        })
    with patch(_CREATE_ORDER):
        resp3 = client.post("/agent/purchase", json={
            "customer_id": "CUST002",
            "product_id": "FD001",
            "quantity": 1,
        })

    txn1 = resp1.json()["transaction_id"]
    txn2 = resp2.json()["transaction_id"]
    txn3 = resp3.json()["transaction_id"]

    # 2. GET /audit without filters -> returns all 3
    list_all = client.get("/audit")
    assert list_all.status_code == 200
    records = list_all.json()
    assert len(records) == 3
    ids = [r["transaction_id"] for r in records]
    assert txn3 in ids and txn2 in ids and txn1 in ids

    # 3. GET /audit?customer_id=CUST002
    list_cust2 = client.get("/audit", params={"customer_id": "CUST002"})
    assert list_cust2.status_code == 200
    cust2_records = list_cust2.json()
    assert len(cust2_records) == 1
    assert cust2_records[0]["transaction_id"] == txn3
    assert cust2_records[0]["decision"] == "REJECTED"

    # 4. GET /audit?decision=APPROVED
    list_approved = client.get("/audit", params={"decision": "APPROVED"})
    assert list_approved.status_code == 200
    approved_records = list_approved.json()
    assert len(approved_records) == 1
    assert approved_records[0]["transaction_id"] == txn1

    # 5. GET /audit?decision=REJECTED
    list_rejected = client.get("/audit", params={"decision": "REJECTED"})
    assert list_rejected.status_code == 200
    rejected_records = list_rejected.json()
    assert len(rejected_records) == 2


def test_get_audit_record_not_found_returns_404():
    """
    GET /audit/{unknown_transaction_id} returns HTTP 404 with descriptive error.
    """
    response = client.get("/audit/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "00000000-0000-0000-0000-000000000000" in data["detail"]

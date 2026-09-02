"""
Tests for Phase 6 — SQLite Audit Trail with SHA-256 Cryptographic Hash Chaining.

Covers:
1. Unit tests for AuditStore (table creation, hash chaining, two-phase writes, PENDING state, listing with filters, get).
2. Tamper-evidence and hash integrity verification (genesis anchor, recomputed SHA-256 validation, corruption detection).
3. Daily spend tracking against mandates.
4. Authentication checks on /audit endpoints (401 on unauthorized).
5. End-to-end integration tests via TestClient (purchase flow -> audit record verification -> cryptographic verification).
6. GET /audit/verify endpoint.
"""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.audit import AuditRecord, AuditStore, compute_audit_hash
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



# ══════════════════════════════════════════════════════════════════════════════

# 1. AuditStore Unit Tests & Hash Chaining
# ══════════════════════════════════════════════════════════════════════════════

def test_audit_store_write_proposal_phase_a(tmp_path):
    """
    Phase A: write_proposal creates an audit record with PENDING payment status for APPROVED,
    computes valid record_hash and links prev_hash.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_a.db"))
    txn_id_app = "txn-unit-001"

    store.write_proposal(
        transaction_id=txn_id_app,
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Transaction amount ₹1499.00 is within mandate limit of ₹2000.00.",
    )

    record = store.get(txn_id_app)
    assert record is not None
    assert record.transaction_id == txn_id_app
    assert record.customer_id == "CUST001"
    assert record.product_id == "KB001"
    assert record.amount == 1499.0
    assert record.decision == "APPROVED"
    assert record.payment_status == "PENDING"
    assert record.prev_hash == "GENESIS"
    assert record.record_hash is not None


def test_audit_hash_chaining_and_integrity_verification(tmp_path):
    """
    Multiple audit entries form an unbroken cryptographic SHA-256 chain.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_chain.db"))

    store.write_proposal(
        transaction_id="txn-chain-1",
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Approved",
        timestamp="2026-09-01T10:00:00Z",
    )
    store.update_payment_outcome(
        transaction_id="txn-chain-1",
        payment_status="created",
        razorpay_order_id="order_1",
    )

    store.write_proposal(
        transaction_id="txn-chain-2",
        customer_id="CUST001",
        product_id="FD001",
        merchant_id="MERCH_FOOD",
        quantity=1,
        amount=349.0,
        decision="APPROVED",
        decision_reason="Approved",
        timestamp="2026-09-01T10:05:00Z",
    )

    res = store.verify_integrity()
    assert res["valid"] is True
    assert res["total_records"] == 3
    assert res["status"] == "VERIFIED_IMMUTABLE"


def test_audit_tamper_detection(tmp_path):
    """
    Directly tampering with an audit event in the database breaks the cryptographic hash chain.
    """
    db_file = str(tmp_path / "unit_test_tamper.db")
    store = AuditStore(db_path=db_file)

    store.write_proposal(
        transaction_id="txn-t1",
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="APPROVED",
        decision_reason="Approved",
    )

    # Tamper with event payload in database directly
    with store._get_connection() as conn:
        conn.cursor().execute("UPDATE audit_events SET payload_json = '{\"tampered\": true}' WHERE transaction_id = 'txn-t1'")
        conn.commit()

    res = store.verify_integrity()
    assert res["valid"] is False
    assert "Corrupted event hash" in res["error"]


def test_audit_get_daily_spend(tmp_path):
    """
    get_daily_spend correctly sums approved transactions for a given customer and date.
    """
    store = AuditStore(db_path=str(tmp_path / "unit_test_spend.db"))

    store.write_proposal(
        transaction_id="txn-s1",
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1000.0,
        decision="APPROVED",
        decision_reason="Approved",
        timestamp="2026-09-02T08:00:00Z",
    )
    store.write_proposal(
        transaction_id="txn-s2",
        customer_id="CUST001",
        product_id="FD001",
        merchant_id="MERCH_FOOD",
        quantity=1,
        amount=500.0,
        decision="APPROVED",
        decision_reason="Approved",
        timestamp="2026-09-02T09:00:00Z",
    )
    store.write_proposal(
        transaction_id="txn-s3",
        customer_id="CUST001",
        product_id="MN001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=4000.0,
        decision="REJECTED",
        decision_reason="Rejected",
        timestamp="2026-09-02T10:00:00Z",
    )

    daily_spend = store.get_daily_spend("CUST001", target_date="2026-09-02")
    assert daily_spend == 1500.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Authentication & Authorization
# ══════════════════════════════════════════════════════════════════════════════

def test_audit_endpoints_require_authentication():
    """
    GET /audit and GET /audit/{id} and GET /audit/verify must return 401 without admin auth.
    """
    assert client.get("/audit").status_code == 401
    assert client.get("/audit/some-id").status_code == 401
    assert client.get("/audit/verify").status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 3. Integration Tests via TestClient
# ══════════════════════════════════════════════════════════════════════════════

def test_purchase_approved_creates_complete_audit_record(admin_headers):
    """
    Approved purchase creates a complete queryable audit record.
    """
    with patch(_CREATE_ORDER, return_value=_FAKE_ORDER):
        response = client.post(
            "/agent/purchase",
            json={
                "customer_id": "CUST001",
                "product_id": "FD001",
                "quantity": 1,
            },
            headers=admin_headers,
        )

    assert response.status_code == 200
    resp_data = response.json()
    txn_id = resp_data["transaction_id"]

    audit_resp = client.get(f"/audit/{txn_id}", headers=admin_headers)
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["transaction_id"] == txn_id
    assert audit_data["decision"] == "APPROVED"
    assert audit_data["payment_status"] == "created"


def test_interleaved_transactions_maintain_cryptographic_integrity(tmp_path):
    """
    Proves that interleaved multi-transaction lifecycles (Tx A propose -> Tx B propose -> Tx A confirm -> Tx B confirm)
    maintain an unbroken, verifiable SHA-256 cryptographic hash chain via append-only event ledger.
    """
    store = AuditStore(db_path=str(tmp_path / "interleaved_ledger.db"))

    # 1. Proposal A evaluated
    store.write_proposal(
        transaction_id="tx-A",
        customer_id="CUST001",
        product_id="KB001",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=1499.0,
        decision="PENDING_CONFIRMATION",
        decision_reason="Gated for human confirmation",
    )

    # 2. Proposal B evaluated (interleaved before A confirms)
    store.write_proposal(
        transaction_id="tx-B",
        customer_id="CUST002",
        product_id="HK002",
        merchant_id="MERCH_ELEC",
        quantity=1,
        amount=899.0,
        decision="PENDING_CONFIRMATION",
        decision_reason="Gated for human confirmation",
    )

    # 3. Tx A confirmed by human
    store.update_payment_outcome(
        transaction_id="tx-A",
        payment_status="created",
        razorpay_order_id="order_tx_A",
    )

    # 4. Tx B confirmed by human
    store.update_payment_outcome(
        transaction_id="tx-B",
        payment_status="created",
        razorpay_order_id="order_tx_B",
    )

    # 5. Verify integrity of ledger
    res = store.verify_integrity()
    assert res["valid"] is True
    assert res["total_records"] == 4  # 4 immutable events: Prop A, Prop B, Conf A, Conf B
    assert res["status"] == "VERIFIED_IMMUTABLE"


def test_verify_audit_ledger_endpoint(admin_headers):
    """
    GET /audit/verify returns successful verification of the audit chain.
    """
    response = client.get("/audit/verify", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "total_records" in data


def test_audit_ledger_anchor_endpoint(admin_headers):
    """
    GET /audit/anchor returns the exportable cryptographic checkpoint and root hash.
    """
    response = client.get("/audit/anchor", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ledger_status"] == "tamper_evident_anchored"
    assert "root_event_hash" in data
    assert "total_event_blocks" in data
    assert "anchor_digest_sha256" in data
    assert "anchored_at" in data



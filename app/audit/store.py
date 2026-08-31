"""
SQLite persistence layer for the audit trail.

Provides an immutable, queryable audit log storing every proposal evaluated by the gateway,
its policy decision verdict, and the final payment execution status.
"""
from datetime import datetime, timezone
import os
import sqlite3
from typing import List, Optional

from app.audit.models import AuditRecord


class AuditStore:
    """
    Manages SQLite database connections and CRUD operations for audit records.
    The table is created automatically on initial use (CREATE TABLE IF NOT EXISTS).
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            raw_url = os.environ.get("DATABASE_URL", "gateway.db")
            # Strip URL scheme if someone configured sqlite:///path/to/db
            if raw_url.startswith("sqlite:///"):
                db_path = raw_url[len("sqlite:///"):]
            elif raw_url.startswith("sqlite://"):
                db_path = raw_url[len("sqlite://"):]
            else:
                db_path = raw_url
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a new SQLite database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        """Ensure the audit_records table exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_records (
                    transaction_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    merchant_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    decision TEXT NOT NULL,
                    decision_reason TEXT NOT NULL,
                    payment_status TEXT,
                    razorpay_order_id TEXT
                );
                """
            )
            conn.commit()

    def write_proposal(
        self,
        transaction_id: str,
        customer_id: str,
        product_id: str,
        merchant_id: str,
        quantity: int,
        amount: float,
        decision: str,
        decision_reason: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Phase A: Record the initial purchase proposal and deterministic policy decision.
        Always executed immediately following policy engine evaluation.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_records (
                    transaction_id, timestamp, customer_id, product_id,
                    merchant_id, quantity, amount, decision, decision_reason,
                    payment_status, razorpay_order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL);
                """,
                (
                    transaction_id,
                    timestamp,
                    customer_id,
                    product_id,
                    merchant_id,
                    quantity,
                    amount,
                    decision,
                    decision_reason,
                )
            )
            conn.commit()

    def update_payment_outcome(
        self,
        transaction_id: str,
        payment_status: Optional[str],
        razorpay_order_id: Optional[str] = None,
    ) -> None:
        """
        Phase B: Update the audit record with the downstream payment execution outcome.
        Executed only when the proposal was APPROVED by policy.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE audit_records
                SET payment_status = ?, razorpay_order_id = ?
                WHERE transaction_id = ?;
                """,
                (payment_status, razorpay_order_id, transaction_id)
            )
            conn.commit()

    def list(
        self,
        customer_id: Optional[str] = None,
        decision: Optional[str] = None,
    ) -> List[AuditRecord]:
        """
        Retrieve audit records ordered newest-first, with optional filtering.
        """
        query = (
            "SELECT transaction_id, timestamp, customer_id, product_id, merchant_id, "
            "quantity, amount, decision, decision_reason, payment_status, razorpay_order_id "
            "FROM audit_records"
        )
        conditions = []
        params = []

        if customer_id:
            conditions.append("customer_id = ?")
            params.append(customer_id)
        if decision:
            conditions.append("UPPER(decision) = ?")
            params.append(decision.strip().upper())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC;"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                AuditRecord(
                    transaction_id=row[0],
                    timestamp=row[1],
                    customer_id=row[2],
                    product_id=row[3],
                    merchant_id=row[4],
                    quantity=row[5],
                    amount=row[6],
                    decision=row[7],
                    decision_reason=row[8],
                    payment_status=row[9],
                    razorpay_order_id=row[10],
                )
                for row in rows
            ]

    def get(self, transaction_id: str) -> Optional[AuditRecord]:
        """
        Retrieve a single audit record by its transaction_id.
        Returns None if not found.
        """
        query = (
            "SELECT transaction_id, timestamp, customer_id, product_id, merchant_id, "
            "quantity, amount, decision, decision_reason, payment_status, razorpay_order_id "
            "FROM audit_records "
            "WHERE transaction_id = ?;"
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (transaction_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return AuditRecord(
                transaction_id=row[0],
                timestamp=row[1],
                customer_id=row[2],
                product_id=row[3],
                merchant_id=row[4],
                quantity=row[5],
                amount=row[6],
                decision=row[7],
                decision_reason=row[8],
                payment_status=row[9],
                razorpay_order_id=row[10],
            )


# Default module-level singleton instance
audit_store = AuditStore()

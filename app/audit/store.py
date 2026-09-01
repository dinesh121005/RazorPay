"""
SQLite persistence layer for the audit trail.

Provides an immutable, queryable audit log storing every proposal evaluated by the gateway,
its policy decision verdict, and the final payment execution status.
"""
import contextlib
from datetime import datetime, timezone
import os
import sqlite3
from typing import Generator, List, Optional

from app.audit.models import AuditRecord


class AuditStore:
    """
    Manages SQLite database connections and CRUD operations for audit records.
    The table is created automatically on initial use (CREATE TABLE IF NOT EXISTS).
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._initialized = False

    @property
    def db_path(self) -> str:
        """Resolve database path lazily from constructor argument or DATABASE_URL."""
        if self._db_path is None:
            raw_url = os.environ.get("DATABASE_URL", "gateway.db")
            if raw_url.startswith("sqlite:///"):
                raw_url = raw_url[len("sqlite:///"):]
            elif raw_url.startswith("sqlite://"):
                raw_url = raw_url[len("sqlite://"):]
            self._db_path = raw_url
        return self._db_path

    @db_path.setter
    def db_path(self, value: str) -> None:
        self._db_path = value
        self._initialized = False

    @contextlib.contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Create a new SQLite database connection with explicit retry timeout and ensure it is closed upon completion."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_db_initialized(self) -> None:
        """Ensure the table schema exists before operations."""
        if not self._initialized:
            self._init_db()
            self._initialized = True

    def _init_db(self) -> None:
        """Ensure the audit_records table exists with all required columns."""
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
                    razorpay_order_id TEXT,
                    idempotency_key TEXT UNIQUE
                );
                """
            )
            # Migration check: add idempotency_key column if table was created in earlier schema
            cursor.execute("PRAGMA table_info(audit_records);")
            columns = [col[1] for col in cursor.fetchall()]
            if "idempotency_key" not in columns:
                cursor.execute("ALTER TABLE audit_records ADD COLUMN idempotency_key TEXT;")
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_idempotency_key ON audit_records(idempotency_key) WHERE idempotency_key IS NOT NULL;"
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
        idempotency_key: Optional[str] = None,
    ) -> None:
        """
        Phase A: Record the initial purchase proposal and deterministic policy decision.
        Always executed immediately following policy engine evaluation.
        For APPROVED proposals, payment_status is initialized to 'PENDING'.
        For REJECTED proposals, payment_status remains NULL (never attempted).
        """
        self._ensure_db_initialized()
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        initial_payment_status = "PENDING" if decision == "APPROVED" else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_records (
                    transaction_id, timestamp, customer_id, product_id,
                    merchant_id, quantity, amount, decision, decision_reason,
                    payment_status, razorpay_order_id, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?);
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
                    initial_payment_status,
                    idempotency_key,
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
        Raises ValueError if transaction_id row does not exist.
        """
        self._ensure_db_initialized()
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
            if cursor.rowcount == 0:
                raise ValueError(f"Audit record '{transaction_id}' not found to update payment outcome")

    def list(
        self,
        customer_id: Optional[str] = None,
        decision: Optional[str] = None,
        payment_status: Optional[str] = None,
    ) -> List[AuditRecord]:
        """
        Retrieve audit records ordered newest-first, with optional filtering.
        """
        self._ensure_db_initialized()
        query = (
            "SELECT transaction_id, timestamp, customer_id, product_id, merchant_id, "
            "quantity, amount, decision, decision_reason, payment_status, razorpay_order_id, idempotency_key "
            "FROM audit_records"
        )
        conditions = []
        params = []

        if customer_id and customer_id.strip():
            conditions.append("customer_id = ?")
            params.append(customer_id.strip())
        if decision and decision.strip():
            conditions.append("UPPER(decision) = ?")
            params.append(decision.strip().upper())
        if payment_status and payment_status.strip():
            conditions.append("payment_status = ?")
            params.append(payment_status.strip())

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
                    idempotency_key=row[11] if len(row) > 11 else None,
                )
                for row in rows
            ]

    def get(self, transaction_id: str) -> Optional[AuditRecord]:
        """
        Retrieve a single audit record by its transaction_id.
        Returns None if not found.
        """
        self._ensure_db_initialized()
        query = (
            "SELECT transaction_id, timestamp, customer_id, product_id, merchant_id, "
            "quantity, amount, decision, decision_reason, payment_status, razorpay_order_id, idempotency_key "
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
                idempotency_key=row[11] if len(row) > 11 else None,
            )

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[AuditRecord]:
        """
        Retrieve a single audit record by its idempotency_key.
        Returns None if not found.
        """
        if not idempotency_key or not idempotency_key.strip():
            return None

        self._ensure_db_initialized()
        query = (
            "SELECT transaction_id, timestamp, customer_id, product_id, merchant_id, "
            "quantity, amount, decision, decision_reason, payment_status, razorpay_order_id, idempotency_key "
            "FROM audit_records "
            "WHERE idempotency_key = ?;"
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (idempotency_key.strip(),))
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
                idempotency_key=row[11] if len(row) > 11 else None,
            )


# Default module-level singleton instance
audit_store = AuditStore()

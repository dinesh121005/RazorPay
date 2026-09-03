import contextlib
import os
import time
from typing import Any, Dict, Generator, Optional, Tuple

DEMO_WALLET_BALANCES: Dict[str, float] = {
    "CUST001": 5000.0,
    "CUST002": 3000.0,
}


class WalletStore:
    """
    Thread-safe persistent storage for customer auto-pay / pre-authorized wallet balances.
    Backed by SQLite or PostgreSQL.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._initialized = False

    @property
    def db_path(self) -> str:
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
    def _get_connection(self) -> Generator[Any, None, None]:
        from app.db import get_db_connection
        with get_db_connection(self.db_path) as conn:
            yield conn

    def _ensure_db_initialized(self) -> None:
        if not self._initialized:
            self._init_db()
            self._initialized = True

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_wallets (
                    customer_id TEXT PRIMARY KEY,
                    balance REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            now = time.time()
            for cid, bal in DEMO_WALLET_BALANCES.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO customer_wallets
                        (customer_id, balance, currency, created_at, updated_at)
                    VALUES (?, ?, 'INR', ?, ?)
                    """,
                    (cid, bal, now, now),
                )
            conn.commit()

    def get_balance(self, customer_id: str) -> float:
        """Return the current auto-pay balance for a customer."""
        self._ensure_db_initialized()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT balance FROM customer_wallets WHERE customer_id = ?",
                (customer_id,),
            )
            row = cursor.fetchone()
            if row:
                return float(row[0])
            # If not yet seeded, provision default ₹2,000 balance
            now = time.time()
            default_balance = 2000.0
            cursor.execute(
                """
                INSERT INTO customer_wallets (customer_id, balance, currency, created_at, updated_at)
                VALUES (?, ?, 'INR', ?, ?)
                """,
                (customer_id, default_balance, now, now),
            )
            conn.commit()
            return default_balance

    def debit(self, customer_id: str, amount: float) -> Tuple[bool, float, str]:
        """
        Atomically debit customer auto-pay balance.
        Returns (success: bool, remaining_balance: float, message: str).
        """
        self._ensure_db_initialized()
        current_bal = self.get_balance(customer_id)
        if current_bal < amount:
            return False, current_bal, f"Insufficient auto-pay balance (₹{current_bal:.2f} < ₹{amount:.2f})"

        now = time.time()
        new_balance = round(current_bal - amount, 2)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE customer_wallets SET balance = ?, updated_at = ? WHERE customer_id = ?",
                (new_balance, now, customer_id),
            )
            conn.commit()
        return True, new_balance, f"Auto-debited ₹{amount:.2f} (Remaining balance: ₹{new_balance:.2f})"

    def credit(self, customer_id: str, amount: float) -> float:
        """Atomically credit customer auto-pay balance."""
        self._ensure_db_initialized()
        current_bal = self.get_balance(customer_id)
        new_balance = round(current_bal + amount, 2)
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE customer_wallets SET balance = ?, updated_at = ? WHERE customer_id = ?",
                (new_balance, now, customer_id),
            )
            conn.commit()
        return new_balance

    def set_balance(self, customer_id: str, balance: float) -> None:
        """Set explicit customer balance (for admin or testing)."""
        self._ensure_db_initialized()
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_wallets (customer_id, balance, currency, created_at, updated_at)
                VALUES (?, ?, 'INR', ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET balance = excluded.balance, updated_at = excluded.updated_at
                """,
                (customer_id, balance, now, now),
            )
            conn.commit()


wallet_store = WalletStore()

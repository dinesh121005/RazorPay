import contextlib
from datetime import datetime, timezone
import json
import os
import sqlite3
import time
from typing import Any, Dict, Generator, List, Optional
from app.policy.mandate import Mandate

# Single source of truth for initial demo customer mandates
DEMO_MANDATES: Dict[str, Mandate] = {
    "CUST001": Mandate(
        customer_id="CUST001",
        display_name="Dinesh Kumar",
        email="dinesh@example.com",
        max_transaction_amount=2000.0,
        currency="INR",
        allowed_categories=["electronics", "home_kitchen", "apparel", "food"],
        allowed_merchants=["MERCH_ELEC", "MERCH_FOOD"],
        expires_at=None,
        prompt_playback="Pre-authorized spending up to ₹2,000 for electronics, home & kitchen, apparel, and food from verified demo merchants (MERCH_ELEC, MERCH_FOOD)."
    ),
    "CUST002": Mandate(
        customer_id="CUST002",
        display_name="Alex Smith",
        email="alex@example.com",
        max_transaction_amount=1500.0,
        currency="INR",
        allowed_categories=["electronics", "home_kitchen"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=None,
        prompt_playback="Pre-authorized spending up to ₹1,500 for electronics and home & kitchen from MERCH_ELEC only."
    ),
}


class MandateStore:
    """
    Persistent storage for customer spending mandates backed by SQLite (and DATABASE_URL).
    Seeded from DEMO_MANDATES on first startup, persists across server restarts and reloads.
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
    def _get_connection(self) -> Generator[Any, None, None]:
        """Create a new database connection (SQLite or PostgreSQL) via universal connection manager."""
        from app.db import get_db_connection
        with get_db_connection(self.db_path) as conn:
            yield conn


    def _ensure_db_initialized(self) -> None:
        """Ensure customer_mandates table exists and seed demo data."""
        if not self._initialized:
            self._init_db()
            self._initialized = True

    def _init_db(self) -> None:
        """Creates table customer_mandates and seeds DEMO_MANDATES if absent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_mandates (
                    customer_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    email TEXT,
                    max_transaction_amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    allowed_categories TEXT NOT NULL,
                    allowed_merchants TEXT NOT NULL,
                    expires_at TEXT,
                    prompt_playback TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_mandates_email ON customer_mandates (email)"
            )
            conn.commit()

            # Seed demo mandates if not present
            now = time.time()
            for m in DEMO_MANDATES.values():
                cursor.execute(
                    "SELECT 1 FROM customer_mandates WHERE customer_id = ?",
                    (m.customer_id,),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        """
                        INSERT INTO customer_mandates (
                            customer_id, display_name, email, max_transaction_amount,
                            currency, allowed_categories, allowed_merchants,
                            expires_at, prompt_playback, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            m.customer_id,
                            m.display_name,
                            m.email,
                            m.max_transaction_amount,
                            m.currency,
                            json.dumps(m.allowed_categories),
                            json.dumps(m.allowed_merchants),
                            m.expires_at.isoformat() if m.expires_at else None,
                            m.prompt_playback,
                            now,
                            now,
                        ),
                    )
            conn.commit()

    def _row_to_mandate(self, row: tuple) -> Mandate:
        """Convert a database row into a Pydantic Mandate instance."""
        (
            customer_id,
            display_name,
            email,
            max_amount,
            currency,
            cats_json,
            merchs_json,
            exp_str,
            playback,
            _,
            _,
        ) = row

        cats = json.loads(cats_json) if isinstance(cats_json, str) else list(cats_json)
        merchs = json.loads(merchs_json) if isinstance(merchs_json, str) else list(merchs_json)
        exp_dt = datetime.fromisoformat(exp_str) if exp_str else None

        return Mandate(
            customer_id=customer_id,
            display_name=display_name,
            email=email,
            max_transaction_amount=float(max_amount),
            currency=currency or "INR",
            allowed_categories=cats,
            allowed_merchants=merchs,
            expires_at=exp_dt,
            prompt_playback=playback,
        )

    def get_mandate(self, customer_id: str) -> Optional[Mandate]:
        """
        Retrieve spending mandate for a specific customer from persistent database.
        Returns None if no mandate is found.
        """
        self._ensure_db_initialized()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT customer_id, display_name, email, max_transaction_amount,
                       currency, allowed_categories, allowed_merchants,
                       expires_at, prompt_playback, created_at, updated_at
                FROM customer_mandates
                WHERE customer_id = ?
                """,
                (customer_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return self._row_to_mandate(row)

    def find_by_identifier(self, identifier: str) -> List[Mandate]:
        """
        Find customer mandates matching a human identifier (name, email, or customer ID).
        Returns list of matching mandates.
        """
        if not identifier or not identifier.strip():
            return []

        clean = identifier.strip().lower()
        self._ensure_db_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT customer_id, display_name, email, max_transaction_amount,
                       currency, allowed_categories, allowed_merchants,
                       expires_at, prompt_playback, created_at, updated_at
                FROM customer_mandates
                """
            )
            rows = cursor.fetchall()

        all_mandates = [self._row_to_mandate(r) for r in rows]
        exact_matches: List[Mandate] = []
        partial_matches: List[Mandate] = []

        for mandate in all_mandates:
            if mandate.email and mandate.email.strip().lower() == clean:
                exact_matches.append(mandate)
                continue
            if mandate.customer_id.strip().lower() == clean:
                exact_matches.append(mandate)
                continue
            if mandate.display_name.strip().lower() == clean:
                exact_matches.append(mandate)
                continue
            if clean in mandate.display_name.strip().lower():
                partial_matches.append(mandate)

        results = exact_matches if exact_matches else partial_matches
        seen = set()
        deduped = []
        for m in results:
            if m.customer_id not in seen:
                seen.add(m.customer_id)
                deduped.append(m)
        return deduped

    def save_mandate(self, mandate: Mandate) -> None:
        """Store or update a customer mandate in SQLite."""
        self._ensure_db_initialized()
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_mandates (
                    customer_id, display_name, email, max_transaction_amount,
                    currency, allowed_categories, allowed_merchants,
                    expires_at, prompt_playback, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    email = excluded.email,
                    max_transaction_amount = excluded.max_transaction_amount,
                    currency = excluded.currency,
                    allowed_categories = excluded.allowed_categories,
                    allowed_merchants = excluded.allowed_merchants,
                    expires_at = excluded.expires_at,
                    prompt_playback = excluded.prompt_playback,
                    updated_at = excluded.updated_at
                """,
                (
                    mandate.customer_id,
                    mandate.display_name,
                    mandate.email,
                    mandate.max_transaction_amount,
                    mandate.currency,
                    json.dumps(mandate.allowed_categories),
                    json.dumps(mandate.allowed_merchants),
                    mandate.expires_at.isoformat() if mandate.expires_at else None,
                    mandate.prompt_playback,
                    now,
                    now,
                ),
            )
            conn.commit()

    def create_mandate(
        self,
        customer_id: str,
        mandate_limit: float,
        allowed_categories: List[str],
        allowed_merchants: List[str],
        display_name: str = "Demo Customer",
        email: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Mandate:
        """Creates and stores a new customer mandate in SQLite."""
        self._ensure_db_initialized()
        existing = self.get_mandate(customer_id)
        if existing:
            raise ValueError(f"Mandate for customer '{customer_id}' already exists")

        cats_str = ", ".join(allowed_categories)
        merchs_str = ", ".join(allowed_merchants)
        playback = (
            f"Pre-authorized spending up to ₹{mandate_limit:,.0f} for {cats_str} "
            f"from verified demo merchants ({merchs_str})."
        )
        mandate = Mandate(
            customer_id=customer_id,
            display_name=display_name,
            email=email,
            max_transaction_amount=mandate_limit,
            currency="INR",
            allowed_categories=allowed_categories,
            allowed_merchants=allowed_merchants,
            expires_at=expires_at,
            prompt_playback=playback,
        )
        self.save_mandate(mandate)
        return mandate.model_copy()

    def update_mandate_limit(
        self,
        customer_id: str,
        new_limit: float,
    ) -> Mandate:
        """Updates the transaction limit for an existing customer mandate in SQLite."""
        self._ensure_db_initialized()
        mandate = self.get_mandate(customer_id)
        if mandate is None:
            raise KeyError(f"Mandate for customer '{customer_id}' not found")

        mandate.max_transaction_amount = new_limit
        cats_str = ", ".join(mandate.allowed_categories)
        merchs_str = ", ".join(mandate.allowed_merchants)
        mandate.prompt_playback = (
            f"Pre-authorized spending up to ₹{new_limit:,.0f} for {cats_str} "
            f"from verified demo merchants ({merchs_str})."
        )
        self.save_mandate(mandate)
        return mandate.model_copy()

    def list_mandates(self) -> Dict[str, Mandate]:
        """List all stored mandates from SQLite."""
        self._ensure_db_initialized()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT customer_id, display_name, email, max_transaction_amount,
                       currency, allowed_categories, allowed_merchants,
                       expires_at, prompt_playback, created_at, updated_at
                FROM customer_mandates
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()

        return {r[0]: self._row_to_mandate(r) for r in rows}

    def delete_mandate(self, customer_id: str) -> bool:
        """Deletes a customer mandate from SQLite."""
        self._ensure_db_initialized()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM customer_mandates WHERE customer_id = ?", (customer_id,))
            conn.commit()
            return cursor.rowcount > 0

    @property
    def _mandates(self) -> Dict[str, Mandate]:
        """Backwards-compatibility property returning dictionary of all mandates."""
        return self.list_mandates()


# Module-level singleton instance
mandate_store = MandateStore()


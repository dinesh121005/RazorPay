from datetime import datetime
from typing import Dict, List, Optional
from app.policy.mandate import Mandate

# Single source of truth for demo customer mandates
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
    # Test-only fixture: authorized for MERCH_ELEC only — used to exercise the
    # merchant-authorization rejection path via POST /agent/purchase.
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
    In-memory storage for customer spending mandates.
    Seeded exclusively from DEMO_MANDATES as the single source of truth.
    """

    def __init__(self):
        # Seed only from DEMO_MANDATES
        self._mandates: Dict[str, Mandate] = {
            k: v.model_copy() for k, v in DEMO_MANDATES.items()
        }

    def get_mandate(self, customer_id: str) -> Optional[Mandate]:
        """
        Retrieve spending mandate for a specific customer.
        Returns None if no mandate is found.
        Returns a defensive copy so internal store state cannot be mutated externally.
        """
        mandate = self._mandates.get(customer_id)
        return mandate.model_copy() if mandate is not None else None

    def find_by_identifier(self, identifier: str) -> List[Mandate]:
        """
        Find customer mandates matching a human identifier (name, email, or customer ID).
        Returns list of matching mandates (defensive copies).
        """
        if not identifier or not identifier.strip():
            return []

        clean = identifier.strip().lower()
        exact_matches: List[Mandate] = []
        partial_matches: List[Mandate] = []

        for mandate in self._mandates.values():
            # 1. Exact email match
            if mandate.email and mandate.email.strip().lower() == clean:
                exact_matches.append(mandate.model_copy())
                continue

            # 2. Exact customer_id match
            if mandate.customer_id.strip().lower() == clean:
                exact_matches.append(mandate.model_copy())
                continue

            # 3. Exact display_name match
            if mandate.display_name.strip().lower() == clean:
                exact_matches.append(mandate.model_copy())
                continue

            # 4. Partial substring display_name match
            if clean in mandate.display_name.strip().lower():
                partial_matches.append(mandate.model_copy())

        # Prioritize exact matches over substring matches if any exact match exists
        results = exact_matches if exact_matches else partial_matches

        # Deduplicate by customer_id preserving order
        seen = set()
        deduped = []
        for m in results:
            if m.customer_id not in seen:
                seen.add(m.customer_id)
                deduped.append(m)
        return deduped

    def save_mandate(self, mandate: Mandate) -> None:
        """
        Store or update a customer mandate.

        Note: This method is reserved for future admin/config tooling and must
        never be called from app/agent/ — the AI agent has no write access to mandates.
        """
        self._mandates[mandate.customer_id] = mandate

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
        """
        Creates and stores a new customer mandate.
        Raises ValueError if customer_id already exists.
        """
        if customer_id in self._mandates:
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
        self._mandates[customer_id] = mandate
        return mandate.model_copy()

    def update_mandate_limit(
        self,
        customer_id: str,
        new_limit: float,
    ) -> Mandate:
        """
        Updates the transaction limit for an existing customer mandate.
        Raises KeyError if customer_id is not found.
        """
        mandate = self._mandates.get(customer_id)
        if mandate is None:
            raise KeyError(f"Mandate for customer '{customer_id}' not found")

        mandate.max_transaction_amount = new_limit
        cats_str = ", ".join(mandate.allowed_categories)
        merchs_str = ", ".join(mandate.allowed_merchants)
        mandate.prompt_playback = (
            f"Pre-authorized spending up to ₹{new_limit:,.0f} for {cats_str} "
            f"from verified demo merchants ({merchs_str})."
        )
        return mandate.model_copy()

    def list_mandates(self) -> Dict[str, Mandate]:
        """
        List all stored mandates.
        Returns a defensive copy so internal store state cannot be mutated externally.
        """
        return {k: v.model_copy() for k, v in self._mandates.items()}


# Module-level singleton instance
mandate_store = MandateStore()

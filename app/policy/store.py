from typing import Dict, Optional
from app.policy.mandate import Mandate

# Single source of truth for demo customer mandates
DEMO_MANDATES: Dict[str, Mandate] = {
    "CUST001": Mandate(
        customer_id="CUST001",
        max_transaction_amount=2000.0,
        currency="INR",
        allowed_categories=["electronics", "home_kitchen", "apparel", "food"],
        allowed_merchants=["MERCH_ELEC", "MERCH_FOOD"],
        expires_at=None,
        prompt_playback="Pre-authorized spending up to \u20b92,000 for electronics, home & kitchen, apparel, and food from verified demo merchants (MERCH_ELEC, MERCH_FOOD)."
    ),
    # Test-only fixture: authorized for MERCH_ELEC only — used to exercise the
    # merchant-authorization rejection path via POST /agent/purchase.
    "CUST002": Mandate(
        customer_id="CUST002",
        max_transaction_amount=1500.0,
        currency="INR",
        allowed_categories=["electronics", "home_kitchen"],
        allowed_merchants=["MERCH_ELEC"],
        expires_at=None,
        prompt_playback="Pre-authorized spending up to \u20b91,500 for electronics and home & kitchen from MERCH_ELEC only."
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
        """
        return self._mandates.get(customer_id)

    def save_mandate(self, mandate: Mandate) -> None:
        """
        Store or update a customer mandate.

        Note: This method is reserved for future admin/config tooling and must
        never be called from app/agent/ — the AI agent has no write access to mandates.
        """
        self._mandates[mandate.customer_id] = mandate

    def list_mandates(self) -> Dict[str, Mandate]:
        """
        List all stored mandates.
        Returns a defensive copy so internal store state cannot be mutated externally.
        """
        return {k: v.model_copy() for k, v in self._mandates.items()}


# Module-level singleton instance
mandate_store = MandateStore()

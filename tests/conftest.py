"""
Shared Pytest configuration and autouse fixtures for the test suite.

Guarantees:
1. DB isolation: every test runs against an isolated, temporary SQLite database.
2. Mandate store reset: in-memory customer mandates are reset to the pristine DEMO_MANDATES baseline.
3. Test environment credentials: set consistent test admin keys and dummy environment vars.
"""
import os
import pytest

# Ensure standard test admin key is present in environment for test client runs
os.environ["ADMIN_API_KEY"] = "test-admin-secret-key"

from app.audit import audit_store
from app.oauth.store import customer_auth_store
from app.policy.store import DEMO_MANDATES, mandate_store


@pytest.fixture(autouse=True)
def isolate_test_environment(tmp_path, monkeypatch):
    """
    Autouse fixture that runs before every test:
    - Points audit_store.db_path and customer_auth_store.db_path to an isolated temporary SQLite database file.
    - Initializes the audit_records and customer_credentials schemas in the temporary database.
    - Resets the in-memory mandate store to DEMO_MANDATES.
    """
    test_db = str(tmp_path / "test_isolated_gateway.db")
    monkeypatch.setattr(audit_store, "db_path", test_db)
    monkeypatch.setattr(customer_auth_store, "db_path", test_db)
    audit_store._init_db()
    customer_auth_store._init_db()

    # Reset mandate store state
    mandate_store._mandates = {
        k: v.model_copy() for k, v in DEMO_MANDATES.items()
    }

    yield test_db


@pytest.fixture
def admin_headers():
    """Returns valid authentication headers for admin and audit endpoint requests."""
    return {"X-Admin-API-Key": "test-admin-secret-key"}

"""
Tests for Admin Web Dashboard endpoint and static assets.
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_admin_dashboard_endpoint():
    """GET /admin/dashboard returns 200 OK and HTML document."""
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert "Agentic Commerce Gateway" in response.text
    assert "Admin Dashboard" in response.text


def test_admin_redirect_to_dashboard():
    """GET /admin redirects to /admin/dashboard."""
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code in [307, 302]
    assert response.headers["location"] == "/admin/dashboard"


def test_dashboard_static_assets():
    """Static assets style.css and app.js are properly served."""
    css_res = client.get("/static/admin/style.css")
    assert css_res.status_code == 200
    assert "var(--bg-main)" in css_res.text

    js_res = client.get("/static/admin/app.js")
    assert js_res.status_code == 200
    assert "class AdminDashboard" in js_res.text

"""
Comprehensive test script querying all endpoints on https://razorpay-c454.onrender.com.
"""
import sys
import json
import httpx
from app.oauth.crypto import create_access_token

sys.stdout.reconfigure(encoding='utf-8')
PROD_BASE = "https://razorpay-c454.onrender.com"

def test_all():
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    token = create_access_token("CUST001")
    
    endpoints = [
        ("GET", "/health", None, None),
        ("GET", "/admin/dashboard", None, None),
        ("GET", "/checkout", None, None),
        ("GET", "/products", None, None),
        ("GET", "/products/KB001", None, None),
        ("GET", "/api/analytics/growth-benchmark", None, None),
        ("GET", "/api/analytics/recommendations", None, None),
        ("GET", "/customer/mandate-info?identifier=dinesh", None, None),
        ("POST", "/mcp", {"Authorization": f"Bearer {token}"}, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_products",
                "arguments": {"query": "keyboard"}
            }
        }),
        ("POST", "/mcp", {"Authorization": f"Bearer {token}"}, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_products",
                "arguments": {"query": "mouse"}
            }
        }),
        ("POST", "/mcp", {"Authorization": f"Bearer {token}"}, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "inquire_merchant",
                "arguments": {"query": "I want a mechanical keyboard under 2000"}
            }
        }),
    ]

    for method, path, headers, body_json in endpoints:
        print(f"\n--- {method} {path} ---")
        try:
            if method == "GET":
                r = client.get(f"{PROD_BASE}{path}", headers=headers)
            else:
                r = client.post(f"{PROD_BASE}{path}", headers=headers, json=body_json)
            
            print(f"Status: {r.status_code}")
            text_snippet = r.text[:400].replace("\n", " ")
            print(f"Body: {text_snippet}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_all()

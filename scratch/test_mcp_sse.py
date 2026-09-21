"""
Diagnostic script testing GET /mcp (SSE handshake) and POST /mcp with various Accept headers.
"""
import sys
from fastapi.testclient import TestClient
from app.main import app
from app.oauth.crypto import create_access_token

sys.stdout.reconfigure(encoding='utf-8')

def test_sse_and_http():
    token = create_access_token(customer_id="CUST001")
    
    with TestClient(app) as client:
        print("=== 1. Testing GET /mcp (SSE handshake) ===")
        r_sse = client.get("/mcp", headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"})
        print(f"GET /mcp status: {r_sse.status_code}")
        print(f"GET /mcp headers: {r_sse.headers}")
        print(f"GET /mcp content snippet: {r_sse.text[:300]}")

        print("\n=== 2. Testing GET /mcp/ (with trailing slash) ===")
        r_sse_slash = client.get("/mcp/", headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"})
        print(f"GET /mcp/ status: {r_sse_slash.status_code}")
        print(f"GET /mcp/ content snippet: {r_sse_slash.text[:300]}")

        print("\n=== 3. Testing POST /mcp with Accept: application/json ===")
        call_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_products",
                "arguments": {"query": "keyboard"}
            }
        }
        r_post_appjson = client.post("/mcp", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, json=call_payload)
        print(f"POST /mcp (application/json) status: {r_post_appjson.status_code}")
        print(f"POST /mcp (application/json) content: {r_post_appjson.text}")

        print("\n=== 4. Testing POST /mcp with Accept: */* ===")
        r_post_star = client.post("/mcp", headers={"Authorization": f"Bearer {token}", "Accept": "*/*"}, json=call_payload)
        print(f"POST /mcp (*/*) status: {r_post_star.status_code}")
        print(f"POST /mcp (*/*) content: {r_post_star.text}")

        print("\n=== 5. Testing POST /mcp/ ===")
        r_post_slash = client.post("/mcp/", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, json=call_payload)
        print(f"POST /mcp/ status: {r_post_slash.status_code}")
        print(f"POST /mcp/ content: {r_post_slash.text}")

if __name__ == "__main__":
    test_sse_and_http()

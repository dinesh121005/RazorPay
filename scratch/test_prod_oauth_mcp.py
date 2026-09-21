"""
Test MCP OAuth authentication against live Render production with claude-demo-secret.
"""
import sys
import httpx

sys.stdout.reconfigure(encoding='utf-8')
PROD_BASE = "https://razorpay-c454.onrender.com"

def test_mcp_auth():
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    
    print("=== 1. Authenticate customer via OAuth token endpoint ===")
    r_auth = client.post(f"{PROD_BASE}/oauth/authorize", headers={"Accept": "application/json"}, data={
        "username": "dinesh",
        "password": "password123",
        "client_id": "claude-desktop-client",
        "redirect_uri": "http://localhost:8080/callback",
        "response_type": "code"
    })
    print(f"Authorize status: {r_auth.status_code}")
    auth_data = r_auth.json()
    code = auth_data["code"]

    r_token = client.post(f"{PROD_BASE}/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost:8080/callback",
        "client_id": "claude-desktop-client",
        "client_secret": "claude-demo-secret"
    })
    print(f"Token status: {r_token.status_code}")
    token_data = r_token.json()
    print(f"Token data: {token_data}")
    prod_access_token = token_data["access_token"]
    print(f"Issued Access Token: {prod_access_token[:30]}...")

    print("\n=== 2. POST /mcp tools/call search_products 'keyboard' ===")
    r_search = client.post(
        f"{PROD_BASE}/mcp",
        headers={"Authorization": f"Bearer {prod_access_token}"},
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "search_products", "arguments": {"query": "keyboard"}}
        }
    )
    print(f"MCP Status: {r_search.status_code}")
    print(f"MCP Response: {r_search.text}")

    print("\n=== 3. POST /mcp tools/call search_products 'mouse' ===")
    r_mouse = client.post(
        f"{PROD_BASE}/mcp",
        headers={"Authorization": f"Bearer {prod_access_token}"},
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "search_products", "arguments": {"query": "mouse"}}
        }
    )
    print(f"MCP Mouse Status: {r_mouse.status_code}")
    print(f"MCP Mouse Response: {r_mouse.text}")

    print("\n=== 4. POST /mcp tools/call inquire_merchant ===")
    r_inquire = client.post(
        f"{PROD_BASE}/mcp",
        headers={"Authorization": f"Bearer {prod_access_token}"},
        json={
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "inquire_merchant", "arguments": {"query": "I want a mechanical keyboard under 2000"}}
        }
    )
    print(f"MCP Inquire Status: {r_inquire.status_code}")
    print(f"MCP Inquire Response: {r_inquire.text[:500]}")

if __name__ == "__main__":
    test_mcp_auth()

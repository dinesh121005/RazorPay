"""
Polls https://razorpay-c454.onrender.com/products until deployment completes and returns 200 OK.
"""
import sys
import time
import httpx
from app.oauth.crypto import create_access_token

sys.stdout.reconfigure(encoding='utf-8')
PROD_BASE = "https://razorpay-c454.onrender.com"

def poll():
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    token = create_access_token("CUST001")
    
    print("Polling Render deployment...", flush=True)
    for i in range(1, 40):
        print(f"--- Attempt {i}/40 ---", flush=True)
        try:
            r = client.get(f"{PROD_BASE}/products")
            print(f"GET /products Status: {r.status_code}", flush=True)
            if r.status_code == 200:
                data = r.json()
                print(f"SUCCESS! Returned {len(data)} products.", flush=True)
                ids = [p["id"] for p in data]
                print(f"Sample product IDs: {ids[:10]}", flush=True)
                kb = next((p for p in data if p["id"] == "KB001"), None)
                mouse = next((p for p in data if "mouse" in p["name"].lower()), None)
                webcam = next((p for p in data if "webcam" in p["name"].lower()), None)
                print(f"KB001: {kb}", flush=True)
                print(f"Mouse: {mouse}", flush=True)
                print(f"Webcam: {webcam}", flush=True)
                
                # Test MCP search_products
                mcp_res = client.post(
                    f"{PROD_BASE}/mcp",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "search_products", "arguments": {"query": "keyboard"}}
                    }
                )
                print(f"MCP search_products 'keyboard': {mcp_res.text[:300]}", flush=True)
                
                mcp_mouse = client.post(
                    f"{PROD_BASE}/mcp",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "search_products", "arguments": {"query": "mouse"}}
                    }
                )
                print(f"MCP search_products 'mouse': {mcp_mouse.text[:300]}", flush=True)

                mcp_inquire = client.post(
                    f"{PROD_BASE}/mcp",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "inquire_merchant", "arguments": {"query": "I want a mechanical keyboard under 2000"}}
                    }
                )
                print(f"MCP inquire_merchant: {mcp_inquire.text[:400]}", flush=True)
                break
            else:
                print(f"Body snippet: {r.text[:200]}", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)
        time.sleep(5)

if __name__ == "__main__":
    poll()

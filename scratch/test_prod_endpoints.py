"""
Script inspecting live production endpoints on https://razorpay-c454.onrender.com.
"""
import sys
import httpx

sys.stdout.reconfigure(encoding='utf-8')
PROD_BASE = "https://razorpay-c454.onrender.com"

def test_endpoints():
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    
    print("=== 1. GET /health ===")
    r_health = client.get(f"{PROD_BASE}/health")
    print(f"Status: {r_health.status_code}")
    print(f"Body: {r_health.text}")
    print(f"Headers: {dict(r_health.headers)}")

    print("\n=== 2. GET /products ===")
    r_products = client.get(f"{PROD_BASE}/products")
    print(f"Status: {r_products.status_code}")
    print(f"Body: {r_products.text[:1000]}")
    print(f"Headers: {dict(r_products.headers)}")

    print("\n=== 3. GET /.well-known/oauth-protected-resource ===")
    r_protected = client.get(f"{PROD_BASE}/.well-known/oauth-protected-resource")
    print(f"Status: {r_protected.status_code}")
    print(f"Body: {r_protected.text}")

    print("\n=== 4. GET /.well-known/oauth-authorization-server ===")
    r_auth_server = client.get(f"{PROD_BASE}/.well-known/oauth-authorization-server")
    print(f"Status: {r_auth_server.status_code}")
    print(f"Body: {r_auth_server.text}")

if __name__ == "__main__":
    test_endpoints()

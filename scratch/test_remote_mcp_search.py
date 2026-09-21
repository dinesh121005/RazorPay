"""
Diagnostic script testing MCP search_products over remote_mcp_server and FastAPI TestClient /mcp.
"""
import sys
import asyncio
import json
from fastapi.testclient import TestClient
from app.main import app
from app.mcp.server import remote_mcp_server
from app.oauth.crypto import create_access_token
from app.catalog.service import search_products

# Ensure stdout handles UTF-8
sys.stdout.reconfigure(encoding='utf-8')

async def test_mcp_direct():
    print("=== 1. Testing search_products via catalog service ===")
    prods = search_products(query="keyboard")
    print(f"Catalog service query='keyboard' returned {len(prods)} products: {[p.name for p in prods]}")
    for p in prods:
        print(f"  ID={p.id}, Name={p.name}, Price={p.price}, Status={p.status}, Stock={p.stock}")

    print("\n=== 2. Testing search_products via remote_mcp_server.call_tool ===")
    res = await remote_mcp_server.call_tool(
        name="search_products",
        arguments={"query": "keyboard"}
    )
    print(f"res content: {res}")
    
    res_mech = await remote_mcp_server.call_tool(
        name="search_products",
        arguments={"query": "mechanical keyboard"}
    )
    print(f"res_mech content: {res_mech}")

    res_inquire = await remote_mcp_server.call_tool(
        name="inquire_merchant",
        arguments={"query": "I want a mechanical keyboard under 2000"}
    )
    print(f"res_inquire content (len={len(str(res_inquire))}): {str(res_inquire)[:200]}")

def test_mcp_http_endpoint():
    print("\n=== 3. Testing POST /mcp via FastAPI TestClient (with lifespan context) ===")
    token = create_access_token(customer_id="CUST001")
    headers = {"Authorization": f"Bearer {token}"}
    
    with TestClient(app) as client:
        # 3a. Initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-buyer-ai", "version": "1.0.0"}
            }
        }
        r_init = client.post("/mcp", headers=headers, json=init_payload)
        print(f"Initialize status: {r_init.status_code}")
        print(f"Initialize response: {r_init.text}")

        # 3b. List tools
        list_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        r_list = client.post("/mcp", headers=headers, json=list_payload)
        print(f"Tools list status: {r_list.status_code}")
        print(f"Tools list response snippet: {r_list.text[:300]}")

        # 3c. Call search_products with query="keyboard"
        call_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_products",
                "arguments": {"query": "keyboard"}
            }
        }
        r_call = client.post("/mcp", headers=headers, json=call_payload)
        print(f"Call search_products status: {r_call.status_code}")
        print(f"Call search_products response: {r_call.text}")

        # 3d. Call search_products with query="mechanical keyboard"
        call_payload_mech = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "search_products",
                "arguments": {"query": "mechanical keyboard"}
            }
        }
        r_call_mech = client.post("/mcp", headers=headers, json=call_payload_mech)
        print(f"Call search_products 'mechanical keyboard' status: {r_call_mech.status_code}")
        print(f"Call search_products 'mechanical keyboard' response: {r_call_mech.text}")

        # 3e. Call inquire_merchant with "I want a mechanical keyboard under 2000"
        call_inquire = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "inquire_merchant",
                "arguments": {"query": "I want a mechanical keyboard under 2000"}
            }
        }
        r_inquire = client.post("/mcp", headers=headers, json=call_inquire)
        print(f"Call inquire_merchant status: {r_inquire.status_code}")
        print(f"Call inquire_merchant response snippet: {r_inquire.text[:400]}")

if __name__ == "__main__":
    asyncio.run(test_mcp_direct())
    test_mcp_http_endpoint()

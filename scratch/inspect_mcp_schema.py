"""
Inspect remote_mcp_server tool schemas and test calling search_products.
"""
import sys
import anyio
import json
from app.mcp.server import remote_mcp_server

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    tools = await remote_mcp_server.list_tools()
    for t in tools:
        if t.name in ("search_products", "inquire_merchant"):
            print(f"\n--- Tool: {t.name} ---")
            print(f"Description: {t.description}")
            schema = getattr(t, "input_schema", getattr(t, "inputSchema", {}))
            print(f"inputSchema: {json.dumps(schema, indent=2)}")

    print("\n--- Direct call_tool search_products ---")
    res1 = await remote_mcp_server.call_tool("search_products", {"query": "keyboard"})
    print(f"search_products 'keyboard': {res1}")

    res2 = await remote_mcp_server.call_tool("search_products", {"query": "mouse"})
    print(f"search_products 'mouse': {res2}")

    print("\n--- Direct call_tool inquire_merchant ---")
    try:
        res3 = await remote_mcp_server.call_tool("inquire_merchant", {"query": "I want a mechanical keyboard under 2000"})
        print(f"inquire_merchant: {res3}")
    except Exception as e:
        print(f"inquire_merchant Exception: {e}")

if __name__ == "__main__":
    anyio.run(main)

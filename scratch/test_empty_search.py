import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
from app.mcp.server import remote_mcp_server

async def main():
    res = await remote_mcp_server.call_tool("search_products", {"query": "nonexistent_xyz_123"})
    print("EMPTY SEARCH RESULT:", res)

asyncio.run(main())

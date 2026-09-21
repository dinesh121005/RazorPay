"""
Test MCPServer serialization behavior with List[dict] vs Dict[str, Any].
"""
import sys
import anyio
import json
from mcp.server.mcpserver import MCPServer

sys.stdout.reconfigure(encoding='utf-8')

server = MCPServer("test-server")

@server.tool(name="search_list")
def search_list() -> list:
    return [{"id": "KB001", "name": "Mechanical Gaming Keyboard"}]

@server.tool(name="search_dict")
def search_dict() -> dict:
    return {"products": [{"id": "KB001", "name": "Mechanical Gaming Keyboard"}]}

@server.tool(name="search_str")
def search_str() -> str:
    return json.dumps([{"id": "KB001", "name": "Mechanical Gaming Keyboard"}])

async def test():
    res_list = await server.call_tool("search_list", {})
    print(f"search_list (returns list): {res_list}")

    res_dict = await server.call_tool("search_dict", {})
    print(f"search_dict (returns dict): {res_dict}")

    res_str = await server.call_tool("search_str", {})
    print(f"search_str (returns str): {res_str}")

if __name__ == "__main__":
    anyio.run(test)

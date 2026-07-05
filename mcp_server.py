
"""
mcp_server.py — MCP server exposing get_available_hours (mock calendar tool)
"""
import asyncio, json
from datetime import date, timedelta
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

MOCK_WEEKLY_FREE_HOURS = {0: 2, 1: 3, 2: 2, 3: 3, 4: 4, 5: 6, 6: 5}  # Mon..Sun

def _get_available_hours(num_days: int) -> dict:
    today = date.today()
    schedule = []
    for i in range(num_days):
        day = today + timedelta(days=i)
        free_hours = MOCK_WEEKLY_FREE_HOURS[day.weekday()]
        schedule.append({"date": day.isoformat(), "weekday": day.strftime("%A"), "available_hours": free_hours})
    return {"schedule": schedule, "total_available_hours": sum(d["available_hours"] for d in schedule)}

server = Server("study-calendar-server")

@server.list_tools()
async def list_tools():
    return [Tool(
        name="get_available_hours",
        description="Returns free study hours per day for the next N days, based on the student calendar.",
        inputSchema={"type": "object", "properties": {"num_days": {"type": "integer"}}, "required": ["num_days"]},
    )]

@server.call_tool()
async def call_tool(name, arguments):
    if name == "get_available_hours":
        result = _get_available_hours(int(arguments.get("num_days", 5)))
        return [TextContent(type="text", text=json.dumps(result))]
    raise ValueError(f"Unknown tool: {name}")

async def _main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(_main())

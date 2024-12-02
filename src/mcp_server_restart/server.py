import os
import json
import logging
import psutil
import subprocess
from typing import Any, Optional
import sys
import asyncio
from mcp.server.models import InitializationOptions
from mcp.server import Server, NotificationOptions
import mcp.types as types
import mcp.server.stdio
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Create a server instance
server = Server("claude-restart-server")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available resources."""
    return [
        types.Resource(
            uri=types.AnyUrl("claude://status"),
            name="Claude Desktop Status",
            description="Current status of the Claude Desktop application",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read Claude Desktop status."""
    try:
        # Try to parse the URI
        if not isinstance(uri, str) or not uri.startswith("claude://"):
            raise ValueError("Unknown resource: Invalid URI scheme")
        
        path = uri.replace("claude://", "")
        if not path or path != "status":
            raise ValueError(f"Unknown resource: {path}")

        # Find Claude process
        claude_processes = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] == 'Claude Desktop':
                    claude_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        status = {
            "running": len(claude_processes) > 0,
            "pid": claude_processes[0].pid if claude_processes else None,
            "timestamp": datetime.now().isoformat()
        }

        return json.dumps(status)
    except Exception as e:
        if "Unknown resource" not in str(e):
            raise ValueError(f"Unknown resource: {str(e)}")
        raise

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="restart_claude",
            description="Restart the Claude Desktop application",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Any) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls for Claude Desktop restart."""
    if name != "restart_claude":
        raise ValueError(f"Unknown tool: {name}")

    result = {"status": "success", "message": ""}

    # Find and terminate existing Claude processes
    claude_processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] == 'Claude Desktop':
                claude_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Terminate existing processes
    if claude_processes:
        try:
            for proc in claude_processes:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    result["message"] += f"Terminated Claude process {proc.pid}. "
                except psutil.TimeoutExpired:
                    result["status"] = "error"
                    result["message"] = "Failed to terminate Claude: timeout"
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                except Exception as e:
                    result["status"] = "error"
                    result["message"] = f"Failed to terminate Claude: {str(e)}"
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

            result["message"] += f"Terminated {len(claude_processes)} existing Claude process(es). "
        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Failed to terminate Claude: {str(e)}"
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # Start new Claude process
    try:
        subprocess.Popen(['open', '-a', 'Claude'])
        result["message"] += "Started new Claude process."
    except Exception as e:
        result["status"] = "error"
        result["message"] = "Failed to start Claude"

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

async def main():
    """Main entry point for the server."""
    initialization_options = InitializationOptions(
        server_name="claude-restart-server",
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        )
    )

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server running with stdio transport")
        await server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=initialization_options
        )

if __name__ == "__main__":
    asyncio.run(main())
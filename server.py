import os
import json
import logging
import psutil
import subprocess
from datetime import datetime
from collections.abc import Sequence
from typing import Any

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claude-restart-server")

# Create a server instance
server = Server("claude-restart-server")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available resources."""
    return [
        types.Resource(
            uri="claude://status",
            name="Claude Desktop Status",
            mimeType="application/json",
            description="Current status of Claude Desktop application"
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read Claude Desktop status."""
    if uri != "claude://status":
        raise ValueError(f"Unknown resource: {uri}")

    claude_process = None
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'Claude' in proc.info['name']:
                claude_process = proc
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    status = {
        "running": claude_process is not None,
        "pid": claude_process.pid if claude_process else None,
        "timestamp": datetime.now().isoformat()
    }
    return json.dumps(status, indent=2)

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
async def handle_call_tool(name: str, arguments: Any) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls for Claude Desktop restart."""
    if name != "restart_claude":
        raise ValueError(f"Unknown tool: {name}")

    result = {"status": "success", "message": ""}
    
    # Send initial progress if token available
    if progress_token := server.request_context.meta.progressToken:
        await server.request_context.session.send_progress_notification(
            progress_token=progress_token,
            progress=0,
            total=2
        )

    # Find and terminate Claude process if running
    claude_process = None
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'Claude' in proc.info['name']:
                claude_process = proc
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if claude_process:
        try:
            claude_process.terminate()
            claude_process.wait(timeout=5)
            result["message"] += "Terminated existing Claude process. "
            logger.info(f"Terminated Claude process with PID {claude_process.pid}")
        except Exception as e:
            logger.error(f"Error terminating Claude process: {e}")
            result["status"] = "error"
            result["message"] = f"Failed to terminate Claude: {str(e)}"
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # Update progress
    if progress_token := server.request_context.meta.progressToken:
        await server.request_context.session.send_progress_notification(
            progress_token=progress_token,
            progress=1,
            total=2
        )

    # Start new Claude process
    try:
        subprocess.Popen(["open", "-a", "Claude"])
        result["message"] += "Started new Claude process."
        logger.info("Started new Claude process")
    except Exception as e:
        logger.error(f"Error starting Claude: {e}")
        result["status"] = "error"
        result["message"] = f"Failed to start Claude: {str(e)}"

    # Final progress update
    if progress_token := server.request_context.meta.progressToken:
        await server.request_context.session.send_progress_notification(
            progress_token=progress_token,
            progress=2,
            total=2
        )

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

async def main():
    """Main entry point for the server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="claude-restart-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

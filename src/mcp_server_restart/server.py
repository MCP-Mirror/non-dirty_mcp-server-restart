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
            name="Claude Status",
            description="Current status of the Claude application",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: types.AnyUrl) -> str:
    """Read Claude status."""
    logger.debug(f"Handling read_resource request for URI: {uri}")
    if uri.scheme != "claude":
        logger.error(f"Unsupported URI scheme: {uri.scheme}")
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    path = str(uri).replace("claude://", "")
    if not path or path != "status":
        logger.error(f"Unknown resource path: {path}")
        raise ValueError(f"Unknown resource path: {path}")

    # Find Claude process
    claude_process = None
    logger.debug("Searching for Claude process...")
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # Handle both dictionary and attribute access for process info
            name = proc.info['name'] if isinstance(proc.info, dict) else proc.info.name
            pid = proc.info['pid'] if isinstance(proc.info, dict) else proc.info.pid
            logger.debug(f"Found process: name={name}, pid={pid}")
            
            if name == 'Claude':
                logger.debug(f"Found Claude process with pid: {pid}")
                # Only consider it a valid process if it has a pid
                if pid is not None and pid > 0:
                    claude_process = proc
                    logger.debug(f"Valid Claude process found with pid: {pid}")
                    break
                else:
                    logger.debug("Claude process found but has invalid pid")
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, AttributeError) as e:
            logger.debug(f"Error accessing process: {e}")
            continue

    is_running = claude_process is not None
    logger.debug(f"Final status - is_running: {is_running}, process: {claude_process}")
    
    status = {
        "running": is_running,
        "pid": claude_process.pid if is_running else None,
        "timestamp": datetime.now().isoformat()
    }
    logger.debug(f"Returning status: {status}")

    return json.dumps(status)

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="restart_claude",
            description="Restart the Claude application",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Any) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls for Claude restart."""
    if name != "restart_claude":
        raise ValueError(f"Unknown tool: {name}")

    result = {"status": "success", "message": ""}

    # Find and terminate existing Claude processes
    claude_processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] == 'Claude':
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

def run_server():
    """Entry point for the package."""
    asyncio.run(main())

if __name__ == "__main__":
    run_server()
# mcp-server-restart

Model Context Protocol (MCP) server for restarting Claude Desktop for Mac

## Features

### Resources

The server provides a status resource:
- `claude://status` - Returns the current status of Claude Desktop
  - Returns JSON with running status, PID, and timestamp
  - MIME type: application/json

### Tools

The server implements one tool:
- `restart_claude` - Restarts the Claude Desktop application
  - Safely terminates existing process if running
  - Launches new instance
  - Provides progress notifications during restart

## Installation

```bash
pip install mcp-server-restart
```

## Configuration

### Claude Desktop Integration

Add the following to your Claude Desktop config file:

On MacOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mcp-server-restart": {
      "enabled": true,
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "mcp_server_restart.server"
      ]
    }
  }
}
```

## Development

### Setup

1. Clone the repository
2. Install dependencies:
```bash
uv venv
uv pip install -e ".[dev]"
```

### Testing

Run the test suite:
```bash
pytest
```

## License

MIT License - see LICENSE file for details
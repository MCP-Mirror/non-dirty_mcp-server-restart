import asyncio
import json
import pytest
import psutil
import subprocess
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os
from pydantic import AnyUrl
from datetime import datetime
import contextvars

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import from the new package structure
from src.mcp_server_restart.server import handle_call_tool, handle_list_tools, handle_list_resources, handle_read_resource, server
from mcp.server import request_ctx
import mcp.types as types

class MockProcess:
    def __init__(self, name, pid=12345):
        self.pid = pid
        self.info = {'name': name, 'pid': self.pid}
        self.terminated = False
        self._wait_timeout = False

    def terminate(self):
        if self._wait_timeout:
            raise psutil.TimeoutExpired(self.pid, 5)
        self.terminated = True

    def wait(self, timeout=None):
        if self._wait_timeout:
            raise psutil.TimeoutExpired(self.pid, timeout or 5)
        pass

    def as_dict(self, attrs=None):
        """Mimic psutil process as_dict method"""
        return self.info

    def set_wait_timeout(self, timeout=True):
        """Helper to simulate wait timeout"""
        self._wait_timeout = timeout

class MockRequestContext:
    def __init__(self, progress_token=None):
        self.meta = MagicMock()
        self.meta.progressToken = progress_token
        self.session = AsyncMock()
        self.session.send_progress_notification = AsyncMock()

@pytest.mark.asyncio
async def test_list_tools():
    """Test that list_tools returns the expected tool."""
    tools = await handle_list_tools()
    assert len(tools) == 1
    assert tools[0].name == "restart_claude"
    assert tools[0].description == "Restart the Claude Desktop application"

@pytest.mark.asyncio
async def test_list_resources():
    """Test that list_resources returns the expected resource."""
    resources = await handle_list_resources()
    assert len(resources) == 1
    assert str(resources[0].uri) == "claude://status"
    assert resources[0].name == "Claude Desktop Status"

@pytest.mark.asyncio
async def test_restart_claude_success():
    """Test successful Claude restart."""
    # Mock the process iteration to return a mock process
    mock_process = MockProcess('Claude Desktop')
    def mock_process_iter(*args, **kwargs):
        return [mock_process]
    
    with patch('psutil.process_iter', mock_process_iter), \
         patch('subprocess.Popen') as mock_popen:
        
        result = await handle_call_tool("restart_claude", {})
        result_data = json.loads(result[0].text)
        
        assert mock_process.terminated
        assert result_data["status"] == "success"
        assert "Terminated 1 existing Claude process(es)" in result_data["message"]
        assert "Started new Claude process" in result_data["message"]

@pytest.mark.asyncio
async def test_restart_claude_no_existing_process():
    """Test Claude restart when no process exists."""
    def mock_process_iter(*args, **kwargs):
        return []
    
    with patch('psutil.process_iter', mock_process_iter), \
         patch('subprocess.Popen') as mock_popen:
        
        result = await handle_call_tool("restart_claude", {})
        result_data = json.loads(result[0].text)
        
        assert result_data["status"] == "success"
        assert "Started new Claude process" in result_data["message"]
        assert mock_popen.called

@pytest.mark.asyncio
async def test_restart_claude_termination_error():
    """Test Claude restart with process termination error."""
    mock_process = MockProcess('Claude Desktop')
    def mock_process_iter(*args, **kwargs):
        return [mock_process]
    
    def mock_terminate():
        raise Exception("Termination failed")
    mock_process.terminate = mock_terminate
    
    with patch('psutil.process_iter', mock_process_iter), \
         patch('subprocess.Popen') as mock_popen:
        
        result = await handle_call_tool("restart_claude", {})
        result_data = json.loads(result[0].text)
        
        assert result_data["status"] == "error"
        assert "Failed to terminate Claude" in result_data["message"]
        assert not mock_popen.called

@pytest.mark.asyncio
async def test_restart_claude_start_error():
    """Test Claude restart with process start error."""
    mock_process = MockProcess('Claude Desktop')
    def mock_process_iter(*args, **kwargs):
        return [mock_process]
    
    def mock_popen(*args, **kwargs):
        raise Exception("Failed to start process")
    
    with patch('psutil.process_iter', mock_process_iter), \
         patch('subprocess.Popen', side_effect=mock_popen):
        
        result = await handle_call_tool("restart_claude", {})
        result_data = json.loads(result[0].text)
        
        assert result_data["status"] == "error"
        assert "Failed to start Claude" in result_data["message"]

@pytest.mark.asyncio
async def test_status_resource_response():
    """Test that the status resource returns correctly formatted JSON."""
    # Test with running process
    mock_process = MockProcess('Claude Desktop', pid=54321)
    def mock_process_iter(*args, **kwargs):
        return [mock_process]
    
    with patch('psutil.process_iter', mock_process_iter):
        result = await handle_read_resource("claude://status")
        data = json.loads(result)
        
        assert isinstance(data, dict)
        assert "running" in data
        assert "pid" in data
        assert "timestamp" in data
        assert data["running"] is True
        assert data["pid"] == 54321
        # Validate timestamp format
        try:
            datetime.strptime(data["timestamp"], "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            datetime.strptime(data["timestamp"], "%Y-%m-%dT%H:%M:%S")
    
    # Test with no process
    def mock_empty_iter(*args, **kwargs):
        return []
    
    with patch('psutil.process_iter', mock_empty_iter):
        result = await handle_read_resource("claude://status")
        data = json.loads(result)
        
        assert data["running"] is False
        assert data["pid"] is None

@pytest.mark.asyncio
async def test_multiple_claude_processes():
    """Test behavior when multiple Claude processes are running."""
    # Create multiple mock processes
    processes = [
        MockProcess('Claude Desktop', pid=1000),
        MockProcess('Claude Desktop', pid=1001),
        MockProcess('Claude Desktop', pid=1002)
    ]
    
    def mock_process_iter(*args, **kwargs):
        return processes
    
    with patch('psutil.process_iter', mock_process_iter), \
         patch('subprocess.Popen') as mock_popen:
        
        result = await handle_call_tool("restart_claude", {})
        result_data = json.loads(result[0].text)
        
        # Verify all processes were terminated
        assert all(p.terminated for p in processes), "Not all processes were terminated"
        assert result_data["status"] == "success"
        assert "Terminated 3 existing Claude process(es)" in result_data["message"]
        assert "Started new Claude process" in result_data["message"]
        assert mock_popen.called

@pytest.mark.asyncio
async def test_invalid_resource_uri():
    """Test handling of invalid resource URIs."""
    invalid_uris = [
        "claude:/status",  # Missing slash
        "claude://invalid",  # Unknown endpoint
        "http://status",  # Wrong scheme
        "claude://status/extra",  # Extra path
    ]
    
    for uri in invalid_uris:
        with pytest.raises(ValueError) as exc_info:
            await handle_read_resource(uri)
        assert "Unknown resource" in str(exc_info.value)

@pytest.mark.asyncio
async def test_process_wait_timeout():
    """Test handling of process termination timeout."""
    # Create mock process that times out
    mock_process = MockProcess('Claude Desktop')
    mock_process.set_wait_timeout(True)
    
    def mock_process_iter(*args, **kwargs):
        return [mock_process]
    
    with patch('psutil.process_iter', mock_process_iter), \
         patch('subprocess.Popen') as mock_popen:
        
        result = await handle_call_tool("restart_claude", {})
        result_data = json.loads(result[0].text)
        
        assert result_data["status"] == "error"
        assert "Failed to terminate Claude" in result_data["message"]
        assert not mock_popen.called  # Should not try to start new process

if __name__ == '__main__':
    pytest.main([__file__])

"""Drive Roblox Studio from the shell or from Python, through its built-in MCP server."""
__version__ = "0.1.0"

from .mcp import McpClient, McpError, Result  # noqa: E402
from .studio import (DriveError, NoStudio, Studio, ToolError, WaitTimeout,  # noqa: E402
                     key_code, parse_key_sequence)

__all__ = ["Studio", "McpClient", "Result", "DriveError", "NoStudio", "ToolError",
           "WaitTimeout", "McpError", "key_code", "parse_key_sequence", "__version__"]

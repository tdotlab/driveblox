"""Find the command that starts Roblox Studio's MCP stdio proxy on this machine.

Studio ships a small proxy (StudioMCP) that talks to the running Studio. Where it
lives depends on the OS:

* Windows: ``%LOCALAPPDATA%\\Roblox\\Versions\\<version>\\StudioMCP.exe`` (Roblox's own
  ``mcp.bat`` points at a hardcoded version folder and can go stale, so we look for
  the executable first and use the batch file only as a fallback).
* macOS: ``/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP`` (the path
  Roblox documents).
* Linux: there is no native Studio. Under Wine (for example through Vinegar) the
  Windows executable sits inside the Wine prefix. This is a best-effort search and
  is not verified; set ``DRIVEBLOX_MCP_CMD`` if it misses.

``DRIVEBLOX_MCP_CMD`` overrides everything. It is either a JSON array
(``["wine", "/path/StudioMCP.exe"]``) or a plain command line.
"""
from __future__ import annotations

import glob
import json
import os
import platform
import shlex
import shutil
from typing import Dict, List, Mapping, Optional, Tuple

ENV_CMD = "DRIVEBLOX_MCP_CMD"

MAC_PATHS = (
    "/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP",
    "~/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP",
)

# Wine prefixes where a Linux install of Studio is likely to live.
LINUX_PREFIXES = (
    "~/.var/app/org.vinegarhq.Vinegar/data/vinegar/prefixes/studio",
    "~/.local/share/vinegar/prefixes/studio",
    "~/.wine",
)

Found = Tuple[List[str], Dict[str, str], str]  # argv, extra environment, how it was found


class NotFound(RuntimeError):
    """No MCP proxy could be located."""


def split_command(text: str, windows: bool = False) -> List[str]:
    """Split an override string. A JSON array wins; otherwise shell-style splitting."""
    text = text.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError as e:
            raise NotFound(f"{ENV_CMD} looks like JSON but does not parse: {e}")
        if not isinstance(parsed, list) or not all(isinstance(p, str) for p in parsed) or not parsed:
            raise NotFound(f"{ENV_CMD} must be a non-empty JSON array of strings")
        return parsed
    if windows:  # keep backslashes; strip the quotes shlex leaves behind
        parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p
                 for p in shlex.split(text, posix=False)]
    else:
        parts = shlex.split(text)
    if not parts:
        raise NotFound(f"{ENV_CMD} is empty")
    return parts


def _newest(paths: List[str]) -> Optional[str]:
    return max(paths, key=os.path.getmtime) if paths else None


def find_command(env: Optional[Mapping[str, str]] = None, system: Optional[str] = None) -> Found:
    """Return ``(argv, extra_env, source)`` for the MCP proxy, or raise NotFound."""
    env = os.environ if env is None else env
    system = system or platform.system()

    override = env.get(ENV_CMD)
    if override:
        return split_command(override, windows=(system == "Windows")), {}, f"${ENV_CMD}"

    if system == "Windows":
        local = env.get("LOCALAPPDATA")
        if local:
            exe = _newest(glob.glob(os.path.join(local, "Roblox", "Versions", "*", "StudioMCP.exe")))
            if exe:
                return [exe], {}, "newest Roblox version folder"
            bat = os.path.join(local, "Roblox", "mcp.bat")
            if os.path.exists(bat):
                return ["cmd.exe", "/c", bat], {}, "Roblox's mcp.bat"
        raise NotFound("StudioMCP.exe not found under %LOCALAPPDATA%\\Roblox\\Versions. "
                       "Install or update Roblox Studio, or set " + ENV_CMD + ".")

    if system == "Darwin":
        for p in MAC_PATHS:
            p = os.path.expanduser(p)
            if os.path.exists(p):
                return [p], {}, "macOS app bundle"
        raise NotFound("StudioMCP not found in /Applications/RobloxStudio.app. "
                       "Install or update Roblox Studio, or set " + ENV_CMD + ".")

    # Linux and anything else: look for the Windows proxy inside a Wine prefix.
    prefixes = [env["WINEPREFIX"]] if env.get("WINEPREFIX") else []
    prefixes += [os.path.expanduser(p) for p in LINUX_PREFIXES]
    for prefix in prefixes:
        pattern = os.path.join(prefix, "drive_c", "users", "*", "AppData", "Local", "Roblox",
                               "Versions", "*", "StudioMCP.exe")
        exe = _newest(glob.glob(pattern))
        if exe:
            wine = shutil.which("wine") or "wine"
            return [wine, exe], {"WINEPREFIX": prefix}, f"Wine prefix {prefix}"
    raise NotFound("No Roblox Studio install found. Roblox has no native Linux build; under Wine "
                   "(for example Vinegar) set " + ENV_CMD + ' to e.g. \'["wine", "/path/to/StudioMCP.exe"]\' '
                   "with WINEPREFIX pointing at the Studio prefix.")

"""High-level control of one running Roblox Studio, for scripts and agents.

    from driveblox import Studio

    with Studio() as s:
        s.play(True)
        s.nav(10, 3, -4)
        s.hold("E", 0.4)
        s.wait_for("workspace.Diner:GetAttribute('Stage') == 'cooked'", timeout=10)
        print(s.lua("return workspace.Diner:GetAttribute('Cash')", dm="server"))
        s.play(False)

Every method that talks to Studio raises :class:`ToolError` if the tool reports an error,
so a script fails loudly instead of carrying on with bad state.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from . import locate
from .mcp import McpClient, McpError, Result, save_images

DM = {"edit": "Edit", "client": "Client", "server": "Server"}
FALSE_SENTINEL = "__driveblox_false__"

# Client-side listener used by Studio.check_input: flags a LocalPlayer attribute when the key arrives.
LISTEN_FOR_KEY = """local lp = game.Players.LocalPlayer
lp:SetAttribute('driveblox_input', nil)
game:GetService('UserInputService').InputBegan:Connect(function(input)
    if input.KeyCode == Enum.KeyCode.{key} then
        lp:SetAttribute('driveblox_input', true)
    end
end)
return 'listening'
"""


def connect_timeout() -> float:
    """Seconds to wait for Studio to connect (env DRIVEBLOX_CONNECT_TIMEOUT, default 25)."""
    try:
        return float(os.environ.get("DRIVEBLOX_CONNECT_TIMEOUT", "25"))
    except ValueError:
        return 25.0


class DriveError(RuntimeError):
    """Base class. ``exit_code`` is what the CLI exits with."""
    exit_code = 1


class NoStudio(DriveError):
    """Studio isn't reachable: not running, MCP not enabled, or proxy not found."""
    exit_code = 3


class ToolError(DriveError):
    """A Studio tool reported an error (``text`` holds its message)."""

    def __init__(self, text: str, tool: str = ""):
        super().__init__(text)
        self.text = text
        self.tool = tool


class WaitTimeout(DriveError):
    """``wait_for`` ran out of time."""


# -- key names ---------------------------------------------------------------
_KEY_ALIASES = {
    "1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five",
    "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine", "0": "Zero",
    "esc": "Escape", "escape": "Escape", "enter": "Return", "return": "Return",
    "space": "Space", "tab": "Tab", "backspace": "Backspace", "delete": "Delete",
    "shift": "LeftShift", "ctrl": "LeftControl", "control": "LeftControl", "alt": "LeftAlt",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
}


def key_code(name: str) -> str:
    """Map a friendly key name (``e``, ``1``, ``esc``, ``shift``) to Roblox's KeyCode name."""
    lowered = name.lower()
    if lowered in _KEY_ALIASES:
        return _KEY_ALIASES[lowered]
    if len(name) == 1:
        return name.upper()
    return name  # already a KeyCode name such as LeftShift or F5; the server validates it


def parse_key_sequence(text: str) -> List[Dict[str, Any]]:
    """Parse ``"down:W wait:800 up:W press:E"`` into keyboard actions."""
    kinds = {"down": "keyDown", "up": "keyUp", "press": "keyPress"}
    actions: List[Dict[str, Any]] = []
    for token in text.split():
        kind, _, val = token.partition(":")
        if kind == "wait" and val.isdigit():
            actions.append({"action": "wait", "wait_time_ms": int(val)})
        elif kind in kinds and val:
            actions.append({"action": kinds[kind], "key_code": key_code(val)})
        else:
            raise ValueError(f"bad key sequence step {token!r} (use down:K up:K press:K wait:MS)")
    return actions


class Studio:
    """A connection to one Studio instance through its built-in MCP server."""

    def __init__(self, studio_id: Optional[str] = None, place: Optional[str] = None,
                 verbose: bool = False, wait: Optional[float] = None,
                 argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        extra_env: Dict[str, str] = dict(env or {})
        self.source = "argv argument"
        if argv is None:
            try:
                argv, found_env, self.source = locate.find_command()
            except locate.NotFound as e:
                raise NoStudio(str(e)) from e
            extra_env = {**found_env, **extra_env}
        self.argv = argv
        if wait is None:
            wait = connect_timeout()
        self.client = McpClient(argv, extra_env, verbose)
        try:
            self.tools = self.client.tools(wait)
            if not self.tools:
                raise NoStudio(self.client.auth_hint()
                               or "Studio published no tools. Is Studio open with 'Enable Studio as MCP server' on?")
            self.studios: List[Dict[str, Any]] = []
            self.id = studio_id or os.environ.get("DRIVEBLOX_STUDIO") or self._pick(place)
        except BaseException:
            self.client.close()
            raise

    @classmethod
    def from_client(cls, client: McpClient, studio_id: str, argv: Optional[List[str]] = None) -> "Studio":
        """Wrap an already-connected client. Doesn't close it for you unless you call close()."""
        self = cls.__new__(cls)
        self.client, self.id, self.argv = client, studio_id, argv or []
        self.source, self.tools, self.studios = "existing client", client.tools(0), []
        return self

    # -- connection -----------------------------------------------------------
    def _pick(self, place: Optional[str]) -> str:
        studios: List[Dict[str, Any]] = []
        for _ in range(40):  # the proxy lists tools a beat before Studio registers
            studios = self.list_studios()
            if place:
                studios = [s for s in studios if place.lower() in json.dumps(s).lower()]
            if studios:
                break
            time.sleep(0.5)
        if not studios:
            raise NoStudio("no Studio instance connected" + (f" matching {place!r}" if place else ""))
        if len(studios) > 1:
            names = ", ".join(f"{s.get('file') or s.get('name')}={s['id']}" for s in studios)
            raise NoStudio(f"several Studios are open; pass --studio ID or --place NAME. Choices: {names}")
        return studios[0]["id"]

    def list_studios(self) -> List[Dict[str, Any]]:
        res = self.client.call("list_roblox_studios")
        try:
            self.studios = res.json().get("studios", [])
        except (ValueError, AttributeError):
            self.studios = []
        return self.studios

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Studio":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- raw access -----------------------------------------------------------
    def call_raw(self, tool: str, args: Optional[Dict[str, Any]] = None, timeout: float = 120) -> Result:
        """Call any tool; returns the Result without raising on tool errors."""
        a = dict(args or {})
        a["studio_id"] = self.id
        return self.client.call(tool, a, timeout=timeout)

    def call(self, tool: str, args: Optional[Dict[str, Any]] = None, timeout: float = 120) -> Result:
        """Call any tool; raises ToolError if it reports an error."""
        res = self.call_raw(tool, args, timeout)
        if res.is_error:
            raise ToolError(res.text, tool)
        return res

    # -- state and code -------------------------------------------------------
    def state(self) -> str:
        return self.call("get_studio_state").text

    def lua(self, code: str, dm: str = "edit", timeout: float = 120) -> str:
        """Run Luau in the Edit, Client or Server datamodel and return its result text."""
        return self.call("execute_luau", {"code": code, "datamodel_type": DM[dm]}, timeout).text

    def wait_for(self, expr: str, dm: str = "server", timeout: float = 15, interval: float = 0.2) -> str:
        """Poll a Luau expression until it is truthy and return its value as text.

        Errors while evaluating (a missing instance, say) count as "not yet", so you can
        wait for things that don't exist at first. Raises WaitTimeout.
        """
        code = (f"local ok, v = pcall(function() return ({expr}) end)\n"
                f"if ok and v then return tostring(v) end\n"
                f"return '{FALSE_SENTINEL}'")
        end = time.time() + timeout
        last = ""
        while True:
            res = self.call_raw("execute_luau", {"code": code, "datamodel_type": DM[dm]})
            last = res.text.strip()
            if not res.is_error and last and last != FALSE_SENTINEL:
                return last
            if time.time() >= end:
                raise WaitTimeout(f"timed out after {timeout:g}s waiting for: {expr}"
                                  + (f" (last: {last})" if last and last != FALSE_SENTINEL else ""))
            time.sleep(interval)

    def play(self, start: bool, ready_timeout: float = 20, focus: bool = False) -> str:
        """Start or stop a Play Solo session. On start, wait for both Client and Server datamodels.

        ``focus=True`` also clicks the game viewport so injected input is delivered; see :meth:`focus`.
        """
        self.call("start_stop_play", {"is_start": start})
        state = self.state()
        if start:
            end = time.time() + ready_timeout
            while not ("Client" in state and "Server" in state) and time.time() < end:
                time.sleep(0.5)
                state = self.state()
            if focus:
                self.focus()
        return state

    def focus(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Click inside Studio's window so the game viewport has real input focus (Windows only).

        Studio's input tools report success even when the game never receives the input;
        it only does once the viewport is focused. Moves the real mouse cursor.
        """
        from . import focus as _focus
        try:
            _focus.focus_viewport(x, y)
        except (_focus.FocusUnsupported, _focus.FocusFailed) as e:
            raise DriveError(str(e)) from e

    def check_input(self, key: str = "Pause", timeout: float = 3.0) -> bool:
        """True if a keystroke sent through the MCP input tools actually reaches the game.

        Starts a playtest if one isn't running (and stops it again), listens for the key on
        the client, sends it, and reports whether the game saw it.
        """
        was_playing = "Client" in self.state()
        if not was_playing:
            self.play(True)
        try:
            self.wait_for("game.Players.LocalPlayer ~= nil", dm="client", timeout=30)
            self.lua(LISTEN_FOR_KEY.format(key=key), dm="client")
            self.key_actions([{"action": "keyPress", "key_code": key_code(key)}])
            try:
                self.wait_for("game.Players.LocalPlayer:GetAttribute('driveblox_input') == true",
                              dm="client", timeout=timeout)
                return True
            except WaitTimeout:
                return False
        finally:
            if not was_playing:
                self.play(False)

    def console(self, last: int = 40, grep: Optional[str] = None) -> str:
        import re
        lines = self.call("get_console_output").text.splitlines()
        if grep:
            rx = re.compile(grep, re.I)
            lines = [ln for ln in lines if rx.search(ln)]
        return "\n".join(lines[-last:])

    def tree(self, path: Optional[str] = None, dm: str = "edit", depth: int = 3, limit: int = 200,
             type: Optional[str] = None, keywords: Optional[str] = None) -> str:
        args: Dict[str, Any] = {"datamodel_type": DM[dm], "max_depth": depth, "head_limit": limit}
        if path:
            args["path"] = path
        if type:
            args["instance_type"] = type
        if keywords:
            args["keywords"] = keywords
        return self.call("search_game_tree", args).text

    def inspect(self, path: str) -> str:
        return self.call("inspect_instance", {"path": path}).text

    # -- input (needs a running playtest: the Client datamodel) ---------------
    def key_actions(self, actions: List[Dict[str, Any]]) -> str:
        return self.call("user_keyboard_input", {"actions": actions, "datamodel_type": "Client"}).text

    def press(self, *keys: str) -> str:
        return self.key_actions([{"action": "keyPress", "key_code": key_code(k)} for k in keys])

    def hold(self, key: str, seconds: float) -> str:
        """Hold a key. ProximityPrompts need at least their HoldDuration, so a tap won't trigger them."""
        return self.key_actions([{"action": "keyDown", "key_code": key_code(key)},
                                 {"action": "wait", "wait_time_ms": int(seconds * 1000)},
                                 {"action": "keyUp", "key_code": key_code(key)}])

    def type_text(self, text: str) -> str:
        return self.key_actions([{"action": "textInput", "text_inputs": text}])

    def keys(self, sequence: str) -> str:
        """Run a key sequence string such as ``"down:W wait:800 up:W"``."""
        return self.key_actions(parse_key_sequence(sequence))

    def click(self, x: Optional[float] = None, y: Optional[float] = None, right: bool = False,
              path: Optional[str] = None) -> str:
        step: Dict[str, Any] = {"action": "moveTo"}
        if path:
            step["instance_path"] = path
        else:
            step.update(x=x, y=y)
        actions = [step, {"action": "mouseButtonClick", "mouse_button": "right" if right else "left"}]
        return self.call("user_mouse_input", {"actions": actions, "datamodel_type": "Client"}).text

    def nav(self, x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None,
            path: Optional[str] = None, speed: float = 1.0, timeout: float = 180) -> str:
        """Walk the player's character to a point or an instance and wait until it arrives."""
        args: Dict[str, Any] = {"datamodel_type": "Client", "speed_multiplier": speed}
        if path:
            args["instance_path"] = path
        elif None not in (x, y, z):
            args.update(x=x, y=y, z=z)
        else:
            raise ValueError("nav needs x, y, z or path")
        return self.call("character_navigation", args, timeout).text

    # -- pictures -------------------------------------------------------------
    def screenshot(self, path: str, camera: Optional[List[float]] = None,
                   look_at: Optional[List[float]] = None) -> List[str]:
        """Capture the edit-time viewport (optionally from a given camera) and save it. Returns file paths."""
        args: Dict[str, Any] = {"capture_id": "ScreenCapture_1"}
        if camera and look_at:
            args.update(camera_position=camera, look_at_position=look_at)
        res = self.call("screen_capture", args)
        if not res.images:
            raise ToolError("screen_capture returned no image: " + res.text, "screen_capture")
        return save_images(res.images, os.path.splitext(path)[0])


__all__ = ["Studio", "connect_timeout", "DriveError", "NoStudio", "ToolError", "WaitTimeout", "McpError",
           "key_code", "parse_key_sequence", "DM"]

"""A stand-in for Studio's MCP stdio proxy, for tests. Speaks just enough of the protocol.

Behaviour is driven by the Luau code it is sent, so tests can script it:
  * code containing BOOM        -> tool error
  * code containing TICK        -> "false" sentinel twice, then "true" (for wait_for)
  * code containing ACTIONS     -> JSON of the last keyboard/mouse actions received
  * code "return 1 + 1"         -> "2"
FAKE_MODE=noauth  -> publishes no tools and logs a 401 to stderr (Studio's MCP toggle off)
FAKE_MODE=two     -> two Studio instances are connected
FAKE_MODE=noinput -> input tools say success but the game never receives the keys
"""
import json
import os
import sys

MODE = os.environ.get("FAKE_MODE", "")
SENTINEL = "__driveblox_false__"
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

TOOLS = [
    {"name": n, "description": n, "inputSchema": {"type": "object", "properties": {"studio_id": {}}, "required": ["studio_id"]}}
    for n in ["list_roblox_studios", "get_studio_state", "execute_luau", "start_stop_play", "get_console_output",
              "user_keyboard_input", "user_mouse_input", "character_navigation", "screen_capture",
              "search_game_tree", "inspect_instance"]
]

state = {"playing": False, "ticks": 0, "last_actions": None, "calls": [], "listening": False, "input_seen": False}


def text(t, error=False):
    return {"content": [{"type": "text", "text": t}], "isError": error}


def call(name, args):
    state["calls"].append(name)
    if name == "list_roblox_studios":
        studios = [{"id": "studio-1", "name": "Place One", "file": "one.rbxl"}]
        if MODE == "two":
            studios.append({"id": "studio-2", "name": "Place Two", "file": "two.rbxl"})
        return text(json.dumps({"studios": studios}))
    if name == "get_studio_state":
        return text("Edit, Client, Server" if state["playing"] else "Edit")
    if name == "start_stop_play":
        state["playing"] = bool(args.get("is_start"))
        return text("ok")
    if name == "get_console_output":
        return text("hello\nwarning: low health\nError: boom\nbye")
    if name in ("user_keyboard_input", "user_mouse_input"):
        state["last_actions"] = args.get("actions")
        if MODE != "noinput" and state["listening"]:  # noinput: Studio says Success but the game sees nothing
            state["input_seen"] = True
        return text("ok")
    if name == "character_navigation":
        state["last_actions"] = {k: v for k, v in args.items() if k != "studio_id"}
        return text("arrived")
    if name == "screen_capture":
        return {"content": [{"type": "image", "mimeType": "image/png", "data": PNG}], "isError": False}
    if name in ("search_game_tree", "inspect_instance"):
        return text(json.dumps(args))
    if name == "execute_luau":
        code = args.get("code", "")
        if "BOOM" in code:
            return text("Luau error: boom", error=True)
        if "ACTIONS" in code:
            return text(json.dumps(state["last_actions"]))
        if "TICK" in code:
            state["ticks"] += 1
            return text("true" if state["ticks"] >= 3 else SENTINEL)
        if "InputBegan" in code:
            state["listening"] = True
            return text("listening")
        if "driveblox_input" in code and "GetAttribute" in code:
            return text("true" if state["input_seen"] else SENTINEL)
        if "CALLS" in code:
            return text(",".join(state["calls"]))
        if code.strip() == "return 1 + 1":
            return text("2")
        return text("ok:" + args.get("datamodel_type", ""))
    return text("unknown tool " + name, error=True)


def main():
    if MODE == "noauth":
        print("proxy: 401 no_auth_header", file=sys.stderr, flush=True)
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:
            continue
        method, rid = msg.get("method"), msg["id"]
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "fake-studio-mcp", "version": "0"}}
        elif method == "tools/list":
            result = {"tools": [] if MODE == "noauth" else TOOLS}
        elif method == "tools/call":
            p = msg["params"]
            result = call(p["name"], p.get("arguments", {}))
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": method}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)


if __name__ == "__main__":
    main()

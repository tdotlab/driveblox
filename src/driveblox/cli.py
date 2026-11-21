"""The ``driveblox`` command line."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from typing import Callable, List, Optional

from . import __version__, locate
from .mcp import McpClient, McpError, save_images
from .studio import DM, DriveError, NoStudio, Studio, ToolError, WaitTimeout, connect_timeout

EPILOG = """\
exit codes: 0 ok | 1 a Studio tool reported an error, or a wait timed out |
            2 usage or protocol error | 3 Studio not reachable (not running, MCP off, proxy not found)

Studio needs Assistant > ... > Manage MCP Servers > 'Enable Studio as MCP server' turned on.
Input commands (key, click, nav) act on the Client datamodel, so run `driveblox play start` first.
Run `driveblox doctor` to check the whole chain.
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="driveblox", description="Drive Roblox Studio from the shell through its built-in MCP server.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"driveblox {__version__}")
    ap.add_argument("--studio", help="Studio instance id (see `driveblox studios`); or set DRIVEBLOX_STUDIO")
    ap.add_argument("--place", help="pick the Studio whose place name or file contains this text")
    ap.add_argument("--wait", type=float, metavar="SECONDS",
                    help="how long to wait for Studio to connect (default 25; or DRIVEBLOX_CONNECT_TIMEOUT)")
    ap.add_argument("-v", "--verbose", action="store_true", help="show the MCP proxy's stderr")
    sp = ap.add_subparsers(dest="cmd", required=True, metavar="command")

    def add(name: str, fn: Callable, help: str):
        p = sp.add_parser(name, help=help, description=help)
        p.set_defaults(fn=fn)
        return p

    p = add("doctor", cmd_doctor, "check the proxy, the connection and a Luau round trip")
    p.add_argument("--input", action="store_true",
                   help="also start a playtest and prove a keystroke reaches the game")
    add("studios", cmd_studios, "list connected Studio instances")
    add("state", cmd_state, "play state and available datamodels")
    add("tools", cmd_tools, "list the MCP tools Studio offers")
    add("schema", cmd_schema, "print one tool's JSON schema").add_argument("tool")
    p = add("play", cmd_play, "start or stop a Play Solo session")
    p.add_argument("mode", choices=["start", "stop"])
    p.add_argument("--focus", action="store_true",
                   help="after starting, click the game viewport so input is delivered (Windows)")

    p = add("focus", cmd_focus, "click inside Studio so the game viewport has input focus (Windows)")
    p.add_argument("x", nargs="?", type=int, help="x in Studio's client area (default: middle)")
    p.add_argument("y", nargs="?", type=int)

    p = add("lua", cmd_lua, "run Luau (from -c, a file, or stdin) and print the result")
    p.add_argument("file", nargs="?", help="a .luau file, or - for stdin")
    p.add_argument("-c", "--code")
    p.add_argument("-d", "--dm", choices=list(DM), default="edit", help="datamodel (default: edit)")
    p.add_argument("--timeout", type=float, default=120)

    p = add("wait", cmd_wait, "poll a Luau expression until it is truthy (state sync, not sleeping)")
    p.add_argument("expr", help="e.g. \"workspace.Diner:GetAttribute('Stage') == 'cooked'\"")
    p.add_argument("-d", "--dm", choices=list(DM), default="server", help="datamodel (default: server)")
    p.add_argument("--timeout", type=float, default=15)
    p.add_argument("--interval", type=float, default=0.2)

    p = add("console", cmd_console, "print the Studio output log")
    p.add_argument("-n", type=int, default=40, help="last N lines")
    p.add_argument("--grep", help="case-insensitive regex filter")

    p = add("tree", cmd_tree, "walk the instance tree")
    p.add_argument("path", nargs="?")
    p.add_argument("-d", "--dm", choices=list(DM), default="edit")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--type", help="only this ClassName")
    p.add_argument("--keywords")

    add("inspect", cmd_inspect, "show one instance's properties").add_argument("path")

    p = add("key", cmd_key, "keyboard input in the playtest")
    p.add_argument("verb", choices=["press", "hold", "type", "seq"],
                   help="press K..., hold K SECONDS, type TEXT, seq \"down:W wait:800 up:W\"")
    p.add_argument("rest", nargs="+")

    p = add("click", cmd_click, "mouse click in the playtest")
    p.add_argument("x", nargs="?", type=float)
    p.add_argument("y", nargs="?", type=float)
    p.add_argument("--path", help="click a GuiObject by instance path instead of x y")
    p.add_argument("--right", action="store_true")

    p = add("nav", cmd_nav, "walk the character to X Y Z or to --path, and wait until it arrives")
    p.add_argument("xyz", nargs="*", type=float)
    p.add_argument("--path")
    p.add_argument("--speed", type=float, default=1.0)

    p = add("shot", cmd_shot, "save an edit-time viewport screenshot")
    p.add_argument("path", help="output file (the extension follows the image type)")
    p.add_argument("--camera", nargs=3, type=float, metavar=("X", "Y", "Z"))
    p.add_argument("--look-at", nargs=3, type=float, metavar=("X", "Y", "Z"))

    p = add("call", cmd_call, "call any MCP tool with a JSON argument object (or @file.json)")
    p.add_argument("tool")
    p.add_argument("json", nargs="?", default="{}")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--save-image", metavar="STEM")

    p = add("batch", cmd_batch, "run many commands over one connection (a file, or - for stdin)")
    p.add_argument("file")
    p.add_argument("--keep-going", action="store_true", help="don't stop at the first failing line")

    add("pause", cmd_pause, "sleep (for batch files)").add_argument("seconds", type=float)
    return ap


# -- commands (each returns an exit code or None for 0) ----------------------------
def _out(text: str) -> None:
    if text:
        print(text)


def cmd_studios(s: Studio, a) -> None:
    print(json.dumps(s.studios or s.list_studios(), indent=2))


def cmd_state(s: Studio, a) -> None:
    _out(s.state())


def cmd_tools(s: Studio, a) -> None:
    for t in s.tools:
        schema = t.get("inputSchema") or {}
        required = set(schema.get("required", []))
        params = ", ".join(("*" if k in required else "") + k
                           for k in schema.get("properties", {}) if k != "studio_id")
        print(f"{t['name']}({params})")


def cmd_schema(s: Studio, a) -> Optional[int]:
    tool = next((t for t in s.tools if t["name"] == a.tool), None)
    if not tool:
        print(f"driveblox: unknown tool {a.tool!r}; try `driveblox tools`", file=sys.stderr)
        return 2
    print(json.dumps(tool, indent=2))


def cmd_play(s: Studio, a) -> None:
    _out(s.play(a.mode == "start", focus=a.focus and a.mode == "start"))


def cmd_focus(s, a) -> None:
    from . import focus
    try:
        x, y = focus.focus_viewport(a.x, a.y)
    except (focus.FocusUnsupported, focus.FocusFailed) as e:
        raise DriveError(str(e)) from e
    print(f"clicked the Studio window at screen ({x}, {y})")


def cmd_lua(s: Studio, a) -> Optional[int]:
    if a.code is not None:
        code = a.code
    elif a.file == "-" or (a.file is None and not sys.stdin.isatty()):
        code = sys.stdin.read()
    elif a.file:
        with open(a.file, encoding="utf-8") as f:
            code = f.read()
    else:
        print("driveblox: give -c CODE, a file, or pipe code on stdin", file=sys.stderr)
        return 2
    _out(s.lua(code, a.dm, a.timeout))


def cmd_wait(s: Studio, a) -> None:
    _out(s.wait_for(a.expr, a.dm, a.timeout, a.interval))


def cmd_console(s: Studio, a) -> None:
    _out(s.console(a.n, a.grep))


def cmd_tree(s: Studio, a) -> None:
    _out(s.tree(a.path, a.dm, a.depth, a.limit, a.type, a.keywords))


def cmd_inspect(s: Studio, a) -> None:
    _out(s.inspect(a.path))


def cmd_key(s: Studio, a) -> Optional[int]:
    if a.verb == "press":
        _out(s.press(*a.rest))
    elif a.verb == "hold":
        if len(a.rest) != 2:
            print("usage: driveblox key hold KEY SECONDS", file=sys.stderr)
            return 2
        _out(s.hold(a.rest[0], float(a.rest[1])))
    elif a.verb == "type":
        _out(s.type_text(" ".join(a.rest)))
    else:
        try:
            _out(s.keys(" ".join(a.rest)))
        except ValueError as e:
            print(f"driveblox: {e}", file=sys.stderr)
            return 2


def cmd_click(s: Studio, a) -> Optional[int]:
    if a.path is None and (a.x is None or a.y is None):
        print("driveblox: give X Y or --path", file=sys.stderr)
        return 2
    _out(s.click(a.x, a.y, a.right, a.path))


def cmd_nav(s: Studio, a) -> Optional[int]:
    if a.path:
        _out(s.nav(path=a.path, speed=a.speed))
    elif len(a.xyz) == 3:
        _out(s.nav(*a.xyz, speed=a.speed))
    else:
        print("driveblox: give X Y Z or --path", file=sys.stderr)
        return 2


def cmd_shot(s: Studio, a) -> None:
    for p in s.screenshot(a.path, a.camera, a.look_at):
        print("image:", p)


def cmd_call(s: Studio, a) -> Optional[int]:
    arg = a.json
    if arg.startswith("@"):
        with open(arg[1:], encoding="utf-8") as f:
            arg = f.read()
    try:
        args = json.loads(arg)
    except ValueError as e:
        print(f"driveblox: arguments are not valid JSON: {e}", file=sys.stderr)
        return 2
    res = s.call_raw(a.tool, args, a.timeout)
    if res.images:
        for p in save_images(res.images, a.save_image or "driveblox_image"):
            print("image:", p)
    if res.is_error:
        print(res.text, file=sys.stderr)
        return 1
    _out(res.text)


def cmd_pause(s: Studio, a) -> None:
    time.sleep(a.seconds)


def cmd_batch(s: Studio, a) -> int:
    """One connection, many commands. Lines are CLI commands without the program name."""
    if a.file == "-":
        lines = sys.stdin.read().splitlines()
    else:
        with open(a.file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    parser = build_parser()
    worst = 0
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        print(f"+ {line}", file=sys.stderr)
        try:
            argv = shlex.split(line)
            ns = parser.parse_args(argv)
        except (ValueError, SystemExit):
            print(f"driveblox: line {n}: cannot parse", file=sys.stderr)
            rc = 2
        else:
            if ns.cmd in ("batch", "doctor"):
                print(f"driveblox: line {n}: '{ns.cmd}' cannot run inside a batch", file=sys.stderr)
                rc = 2
            else:
                rc = run(s, ns)
        if rc:
            worst = max(worst, rc)
            if not a.keep_going:
                print(f"driveblox: stopped at line {n} (exit {rc})", file=sys.stderr)
                return rc
    return worst


def cmd_doctor(_s, a) -> int:
    """Check each link in the chain and say what to fix. Safe: it only reads."""
    ok = True

    def step(label: str, passed: bool, detail: str = "") -> bool:
        print(f"[{'ok' if passed else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
        return passed

    try:
        argv, env, source = locate.find_command()
    except locate.NotFound as e:
        step("find the MCP proxy", False, str(e))
        return 3
    step("find the MCP proxy", True, f"{' '.join(argv)}  ({source})")

    try:
        client = McpClient(argv, env, a.verbose)
    except McpError as e:
        step("start the proxy", False, str(e))
        return 3
    try:
        step("start the proxy", True, str(client.server_info.get("name", "")) or "initialized")
        tools = client.tools(wait=a.wait if a.wait is not None else connect_timeout())
        if not tools:
            step("list tools", False, client.auth_hint() or "no tools published; is Studio open?")
            client.close()
            return 3
        step("list tools", True, f"{len(tools)} tools")
        studios = []
        for _ in range(20):
            res = client.call("list_roblox_studios")
            try:
                studios = res.json().get("studios", [])
            except (ValueError, AttributeError):
                studios = []
            if studios:
                break
            time.sleep(0.5)
        if not step("find an open Studio", bool(studios),
                    ", ".join(f"{x.get('file') or x.get('name')} ({x['id']})" for x in studios)
                    or "none connected; open a place in Studio"):
            client.close()
            return 3
        target = a.studio or studios[0]["id"]
        res = client.call("get_studio_state", {"studio_id": target})
        state_text = res.text.strip()
        step("read Studio state", not res.is_error, state_text.replace("\n", " ")[:120])
        # A running playtest has no Edit datamodel, so check Luau in whichever one exists.
        dm = "Client" if "Client" in state_text else "Edit"
        res = client.call("execute_luau", {"code": "return 1 + 1", "datamodel_type": dm, "studio_id": target})
        ok = step(f"run Luau in the {dm} datamodel", not res.is_error and res.text.strip() == "2", res.text.strip())
    except McpError as e:
        step("talk to Studio", False, str(e))
        client.close()
        return 2

    try:
        if ok and a.input:
            try:
                if Studio.from_client(client, target, argv).check_input():
                    step("keystroke reaches the game", True)
                else:
                    ok = step("keystroke reaches the game", False,
                              "Studio said Success but the game never saw the key. Click once inside the Studio "
                              "game viewport (Windows: `driveblox focus`) and run this again.")
            except (DriveError, McpError) as e:
                ok = step("keystroke reaches the game", False, str(e))
    finally:
        client.close()
    print("all good" if ok else "something failed above")
    return 0 if ok else 1


# -- dispatch ----------------------------------------------------------------------
def run(s: Studio, ns) -> int:
    """Run one parsed command against an open Studio, mapping errors to exit codes."""
    try:
        return ns.fn(s, ns) or 0
    except ToolError as e:
        print(e.text, file=sys.stderr)
        return 1
    except DriveError as e:
        print(f"driveblox: {e}", file=sys.stderr)
        return e.exit_code
    except McpError as e:
        print(f"driveblox: {e}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"driveblox: {e}", file=sys.stderr)
        return 2


def main(argv: Optional[List[str]] = None) -> int:
    ns = build_parser().parse_args(argv)
    try:
        if ns.cmd == "doctor":
            return cmd_doctor(None, ns)
        if ns.cmd == "focus":  # needs no MCP connection
            return run(None, ns)
        with Studio(ns.studio, ns.place, ns.verbose, ns.wait) as s:
            return run(s, ns)
    except NoStudio as e:
        print(f"driveblox: {e}", file=sys.stderr)
        return 3
    except DriveError as e:
        print(f"driveblox: {e}", file=sys.stderr)
        return e.exit_code
    except McpError as e:
        print(f"driveblox: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

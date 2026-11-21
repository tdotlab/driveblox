# driveblox

Drive Roblox Studio from the shell or from Python. It speaks to the MCP server that Studio now ships with, so you can start a playtest, run Luau, press keys, walk a character around, wait on game state and read the console, all from a command line or a script, with no MCP client in the way.

```console
$ driveblox play start
$ driveblox nav 12 3 -5
$ driveblox key hold e 1.2
$ driveblox wait "workspace.Diner:GetAttribute('Stage') == 'served'" --timeout 12
$ driveblox console --grep error
$ driveblox play stop
```

Zero dependencies. Python 3.9 or newer. MIT licensed. Not affiliated with or endorsed by Roblox.

## Why this exists

Studio's built-in MCP server is fine if your agent speaks MCP. Plenty of setups do not: a shell-only agent, a CI job, a script you wrote by hand, an editor whose integration list is short. Driveblox puts a command line in front of the same server, and it adds three things the raw tools do not give you.

One process, many steps. Every MCP call from a chat agent is a model round trip. A script that holds a connection open does thousands of calls without one, which is the difference between a test that can catch a 2.5 second tip window and one that cannot. `driveblox batch` and the Python API both run everything over a single connection.

State sync instead of sleeping. `driveblox wait` polls a Luau expression until it is truthy, so a script waits for the game to be ready rather than guessing how long that takes.

A fix for the silent input failure, which deserves its own section.

## The input gotcha (read this)

Studio's input tools (`user_keyboard_input`, `user_mouse_input`, `character_navigation`) return "Success" even when the game never received the input. During a playtest the game only gets keys once its viewport has real operating system window focus. After a fresh playtest, a click elsewhere in Studio, or switching apps, focus can be lost, and then your script runs cleanly and does nothing at all.

Driveblox deals with this in two ways. `driveblox doctor --input` starts a playtest, listens for a key inside the game, sends one, and tells you whether it arrived. On Windows, `driveblox focus` (or `driveblox play start --focus`) clicks inside the Studio window to restore focus. It moves your real mouse cursor, so do not use the mouse while it runs. Elsewhere, click once inside the game viewport yourself before the script starts.

## Install

```console
pipx install git+https://github.com/tdotlab/driveblox
```

or `pip install git+https://github.com/tdotlab/driveblox`, or clone and `pip install -e .`.

Then turn the server on inside Studio: Assistant, then the menu, then Manage MCP Servers, then enable **Enable Studio as MCP server**. Keep Studio open with a place loaded. With the toggle off, the proxy gets a 401 and publishes no tools; driveblox says so and tells you where the switch is.

Check the whole chain:

```console
$ driveblox doctor --input
[ok] find the MCP proxy
[ok] start the proxy
[ok] list tools: 39 tools
[ok] find an open Studio
[ok] read Studio state
[ok] run Luau in the Edit datamodel: 2
[ok] keystroke reaches the game
all good
```

## Commands

Everything prints plain text or JSON to stdout, errors to stderr, and uses a small set of exit codes (below). Run `driveblox <command> --help` for details.

| Command | What it does |
| --- | --- |
| `doctor [--input]` | Check proxy, connection, Luau round trip; with `--input`, prove a keystroke reaches the game |
| `studios`, `state`, `tools`, `schema TOOL` | See what is connected and what Studio offers |
| `play start\|stop [--focus]` | Start or stop Play Solo, waiting until both Client and Server datamodels exist |
| `lua [-d edit\|client\|server] [-c CODE \| FILE \| -]` | Run Luau and print the result |
| `wait EXPR [-d DM] [--timeout S] [--interval S]` | Poll a Luau expression until truthy |
| `key press K...`, `key hold K SECONDS`, `key type TEXT`, `key seq "down:W wait:800 up:W"` | Keyboard input in the playtest |
| `click X Y [--right]`, `click --path PATH` | Mouse click by position or by GuiObject path |
| `nav X Y Z [--speed N]`, `nav --path PATH` | Walk the character somewhere and wait until it arrives |
| `console [-n N] [--grep RE]` | Studio output log |
| `tree`, `inspect` | Walk the instance tree, read an instance's properties |
| `shot FILE` | Edit-time viewport screenshot |
| `call TOOL '{json}'` | Call any MCP tool directly |
| `batch FILE\|-` | Run many commands over one connection |
| `focus [X Y]` | Windows: click the viewport so it has input focus |

Input commands act on the Client datamodel, so run `play start` first.

### Batch

A batch file is one command per line, `#` for comments. They run in order over one connection and stop at the first failure unless you pass `--keep-going`.

```
play start --focus
wait "game.Players.LocalPlayer.Character ~= nil" -d client --timeout 30
nav 0 3 10
key hold e 1.2
wait "workspace.Diner:GetAttribute('Stage') == 'cooked'" --timeout 12
console --grep error
play stop
```

```console
$ driveblox batch playthrough.batch
```

### Python

```python
from driveblox import Studio

with Studio() as s:
    s.play(True, focus=True)
    s.wait_for("#game.Players:GetPlayers() == 1", dm="server")
    s.nav(12, 3, -5)
    s.hold("e", 1.2)
    s.wait_for("workspace.Diner:GetAttribute('Stage') == 'cooked'", timeout=12)
    print(s.lua("return workspace.Diner:GetAttribute('Cash')", dm="server"))
    s.play(False)
```

`examples/` has a smoke test that works on any place, and a full scripted playthrough of a small diner game that shows the pattern: no screenshots, sync on attributes the server publishes, one connection start to finish.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | OK |
| 1 | A Studio tool reported an error, or a `wait` timed out |
| 2 | Usage or protocol error |
| 3 | Studio not reachable: not running, MCP toggle off, or proxy not found |

## Environment

| Variable | Effect |
| --- | --- |
| `DRIVEBLOX_MCP_CMD` | Command that starts the MCP proxy, as a JSON array or a plain command line. Overrides discovery |
| `DRIVEBLOX_STUDIO` | Studio instance id when several are open (or use `--studio`, `--place`) |
| `DRIVEBLOX_CONNECT_TIMEOUT` | Seconds to wait for Studio to connect (default 25) |

## Platform status

I want this to be straight with you, because only one of these has actually been run.

Windows is tested against a live Studio: the doctor, the batch runner, the input checks and a full scripted playthrough. Driveblox looks for `StudioMCP.exe` under `%LOCALAPPDATA%\Roblox\Versions` and takes the newest. Roblox's own `mcp.bat` points at a hardcoded version folder and goes stale after updates, which is why it is only a fallback.

macOS is written from Roblox's documentation (`/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP`) and has not been run. The test suite does run on macOS in CI, against a fake server.

Linux has no native Studio. The only route is Wine, usually through Vinegar, and whether Studio's built-in MCP server works there is unverified. Driveblox searches the usual Vinegar and Wine prefixes for `StudioMCP.exe` and launches it with `wine`. If it misses, point it at the right place:

```console
export DRIVEBLOX_MCP_CMD='["wine", "/path/to/prefix/drive_c/users/me/AppData/Local/Roblox/Versions/version-xxxx/StudioMCP.exe"]'
export WINEPREFIX=/path/to/prefix
driveblox doctor
```

Studio on a different machine than the agent is the more realistic setup for a Linux or headless agent: the proxy talks to Studio over localhost, so driveblox has to run on the machine that runs Studio. Have the agent reach it over SSH, for example `ssh my-windows-box driveblox play start`, or run whole batch files there. This is untested, and one caveat is certain: a non-interactive SSH session has no desktop, so `driveblox focus` and real input focus will not work from it. Check with `driveblox doctor --input` over that same SSH route before trusting any input script.

`driveblox focus` is Windows-only. On X11 you can try restoring viewport focus with xdotool, for example `xdotool search --name "Roblox Studio" windowactivate --sync click 1`, then confirm with `driveblox doctor --input`. If you get Linux working, a note on what you did would be very welcome (see Contributing).

## Security

Anything that can talk to Studio's MCP server can read and modify the place you have open, and run arbitrary Luau in it. The server is local to your machine and gated by the toggle in Studio, but treat the toggle accordingly: leave it off when you are not using it, and do not run scripts you have not read. Driveblox adds no network access of its own.

## For other agents

[docs/for-agents.md](docs/for-agents.md) has a short block you can paste into an `AGENTS.md` or `CLAUDE.md` so a shell-only agent knows how to use this.

## Contributing

Issues and pull requests are welcome, especially reports from macOS and Linux. Run the tests with `python -m unittest discover -s tests -v`. They use a fake MCP server, so they need no Studio. When you report a platform problem, include the output of `driveblox -v doctor --input`.

## License

MIT. See [LICENSE](LICENSE).

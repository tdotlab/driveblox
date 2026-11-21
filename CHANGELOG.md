# Changelog

## 0.1.0

First release.

- CLI and Python API over Studio's built-in MCP server: play control, Luau in Edit/Client/Server, keyboard, mouse and character navigation, console, tree and instance inspection, screenshots, raw tool calls.
- `batch` runs many commands over one connection; `wait` polls a Luau expression instead of sleeping.
- `doctor` checks the whole chain; `doctor --input` proves a keystroke reaches the game.
- `focus` and `play --focus` restore viewport input focus on Windows.
- Proxy discovery for Windows (tested), macOS (from Roblox's docs, untested) and Linux via Wine (best effort, untested). `DRIVEBLOX_MCP_CMD` overrides it.

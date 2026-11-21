# driveblox

CLI and Python library that drives Roblox Studio through its built-in MCP server. Stdlib only, Python 3.9+.

- Code: `src/driveblox/` (`mcp.py` stdio JSON-RPC client, `locate.py` finds the proxy per OS, `studio.py` high-level API, `cli.py` commands, `focus.py` Windows viewport click).
- Tests: `python -m unittest discover -s tests -v`. They run against `tests/fake_studio_mcp.py`, so no Studio is needed. Add a fake-server path for any new behavior.
- Examples: `examples/`. Agent usage snippet: `docs/for-agents.md`.
- Keep the README's command table and exit codes in step with `cli.py`.
- Platform truth: Windows is tested against live Studio; macOS and Linux (Wine) are unverified. Do not claim otherwise.
- Gotcha that shaped the design: Studio's input tools return success even when the game gets nothing unless the viewport has real OS focus. `doctor --input` detects it.
- No personal paths, usernames or emails in the repo or in test output.

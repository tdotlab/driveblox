# Using driveblox from an agent

Paste this block into the `AGENTS.md` or `CLAUDE.md` of a Roblox project so a shell-only agent can test the game itself.

```markdown
## Testing in Roblox Studio

Studio must be open with the place loaded and Assistant > Manage MCP Servers > "Enable Studio as MCP server" on.
Use the `driveblox` CLI; do not guess at timing, sync on game state.

- First run `driveblox doctor --input`. If the keystroke check fails, click once inside the Studio game viewport (Windows: `driveblox focus`) and rerun. Studio reports input as successful even when the game receives nothing.
- `driveblox play start --focus` / `play stop` start and stop a playtest. Input commands (`key`, `click`, `nav`) need a running playtest.
- Wait on state, never on sleeps: `driveblox wait "workspace.X:GetAttribute('Done') == true" --timeout 15` (server datamodel by default, `-d client` for UI).
- Read results with `driveblox lua -d server -c "return ..."` and `driveblox console --grep error`.
- For anything longer than a few steps, write a batch file or a Python script (`from driveblox import Studio`) so it runs over one connection. See examples/ in the driveblox repo.
- Exit codes: 0 ok, 1 tool error or wait timeout, 2 usage error, 3 Studio not reachable.
- Always `driveblox play stop` when done.
```

Have the game publish simple attributes (a stage name, a score, a flag) on a server-side instance. They make waits and assertions one line each, and no screenshots are needed.

## If your agent can't run Studio at all

Studio only runs on Windows and macOS. An agent on Linux, or in a headless VM, can't host it, and that's fine: it can still do the writing while someone else runs the game. Hand over three things in the repo:

1. The Luau source, laid out so it builds into a place without hand-editing.
2. A game that publishes simple state as attributes on a server-side instance (a stage name, a score, a flag), so tests can wait on them.
3. A `tests/*.batch` file or a short Python script using `from driveblox import Studio` that plays the game and asserts on those attributes. See `examples/` for the pattern.

The person with Studio pulls the repo, opens the place, runs `driveblox doctor --input`, then the batch file, and sends back the output. Exit codes tell you what happened: 0 passed, 1 a tool error or a timed-out wait, 3 Studio wasn't reachable.

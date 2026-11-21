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

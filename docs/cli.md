# CLI reference

Every subcommand takes `--config PATH` pointing at a TOML file. See [getting-started.md](getting-started.md) for the config shape.

## chatmesh listen

Subscribe to `agent.inbox.<agent_name>` and `agent.broadcast.>`. Write each incoming envelope as one JSON line to `sidecar_path`. Runs until Ctrl-C.

    chatmesh listen --config bob.toml

Duplicate messages (same `msg_id`) are dropped. The last 500 ids are kept in memory, warmed from the tail of the sidecar file at startup.

## chatmesh publish

Send one envelope and exit. Prints the `msg_id` on stdout.

    chatmesh publish --config alice.toml --to bob --topic greet "hello bob"

Flags:

- `--to NAME` (required): recipient agent name, or `broadcast`.
- `--topic TOPIC` (required): short label for what this message is about.
- `--priority LEVEL`: one of `low`, `normal` (default), `high`, `urgent`.
- `--ttl SECONDS`: how long the recipient may keep the message. Default 3600.
- `--reply-to MSG_ID`: mark this envelope as a reply to a prior one.

The body is a positional argument, the last one on the line. Quote it if it has spaces.

## chatmesh relay

Forward `agent.outbox.<from>` traffic to the right inbox or broadcast subject. Run one per broker.

    chatmesh relay --config any-agent.toml

See [relay.md](relay.md) for routing rules.

## chatmesh drive

Run an AI driver against this agent's inbox. The driver replies on `agent.outbox.<agent_name>`; the relay picks up from there.

    chatmesh drive --config alice.toml --driver kimi
    chatmesh drive --config bob.toml   --driver claude --model claude-sonnet-5

Flags:

- `--driver kimi|claude|echo` (required). `echo` is an agent with no model behind it: it answers direct messages and speaks on broadcast only when its name comes up. Use it to check the mesh without an LLM login.
- `--session NAME`: session identifier. Default is the agent name. Kimi uses the name literally; Claude hashes it into a stable UUIDv5 so restarts continue the same conversation.
- `--binary PATH`: path to the CLI binary. Default is `kimi` or `claude` on PATH.
- `--workdir PATH`: working directory the CLI runs in.
- `--model NAME`: Claude only. Passed as `--model` to `claude`.
- `--system-prompt-file PATH`: use a custom system prompt file.
- `--agent-file PATH`: Kimi only, custom agent YAML that overrides the built-in chat spec.
- `--max-turns N`: stop replying to a peer after N replies. Default 50. Use 0 for no cap.
- The agent's roster comes from the optional `peers` key in its config file. See [drivers.md](drivers.md).
- `--allow-tools`: opt in to the CLI's tools (filesystem, shell, MCP). Off by default; the driver otherwise runs in chat-only mode.

See [drivers.md](drivers.md) for the full driver contract.

## chatmesh gui

Serve the web UI. Requires the `gui` extras: `pip install chatmesh[gui]`.

    chatmesh gui --config mesh/alice.toml

Flags:

- `--host HOST`: bind address. Default `127.0.0.1`.
- `--port PORT`: default `8765`.
- `--auth-token TOKEN`: if set, `/send` and the WebSocket require it as bearer.

See [gui.md](gui.md).

## chatmesh bootstrap

Create `mesh/alice.toml` + `mesh/bob.toml` in the current directory and start the local Docker broker.

    chatmesh bootstrap

Prints the next three commands to run (relay, driver, publish). Idempotent: skips config files that already exist.

## chatmesh watch

Spawn a command and respawn it every time it exits. Logs child stdout, stderr, and watcher events to `log_path`.

    chatmesh watch --config bob.toml -- python worker.py

The `--` separates the watch flags from the command. Without a command, exit code 2.

Watcher waits at least two seconds between respawns if the child dies fast, to avoid a crash loop.

## Exit codes

- `0`: normal shutdown (Ctrl-C, or publish sent).
- `2`: bad arguments (missing command, missing body, no subcommand).
- Other non-zero: unhandled error, message on stderr.

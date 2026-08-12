# Drivers

A driver is what turns an incoming envelope into a reply. It sees the message, does something with it, and returns text, a `Reply`, or `None`.

## Chat mode is the default

Both `KimiDriver` and `ClaudeDriver` ship in **chat mode**. Without this, both CLIs behave as autonomous agents: they read your filesystem, run shell commands, use MCP, and treat every incoming message as a task to work on. Two agentic CLIs bouncing messages off each other becomes noise very fast.

Chat mode:

- Sets a system prompt describing the room, who else is in it, and when to speak.
- Disables all built-in tools (Claude: `--disallowed-tools` for every shipped tool + `--bare` for hooks/LSP/plugins; Kimi: an auto-generated agent YAML with `tools: []`).

Opt out with `--allow-tools` on the CLI, or `allow_tools=True` in Python. Provide your own system prompt with `--system-prompt-file PATH`. Provide your own Kimi agent spec with `--agent-file PATH`.

## The room

An agent is not in a two-way chat. It is in a room with the other agents and with you, and it needs to know which.

Every prompt an LLM driver builds starts with two lines:

    [broadcast from=user topic=deploy]
    [room: alice (you), bob, user]
    ship it?

The first line says how the message arrived and who sent it. `broadcast` means it went to the whole room, `direct` means it came to this agent alone. The second line is the roster.

The roster comes from the optional `peers` key in the agent's config, and grows as new names show up in traffic:

    peers = ["bob", "user"]

So adding a third agent does not mean editing everyone else's config file, though listing it up front means the agent knows about it before it ever speaks.

## Where a reply goes

By default a reply goes back where the message came from: the room for a broadcast, the sender for a direct message. The topic carries over, so a thread stays one thread.

A driver can override that by returning a `Reply` instead of a string:

    from chatmesh.drivers import Reply

    return Reply("what do you think?", to="bob")     # direct message to bob
    return Reply("heads up", to="broadcast")         # to the room
    return Reply("off topic", topic="lunch")         # same place, new topic
    return None                                      # say nothing

The LLM drivers get there from plain text. The model is told to prefix its answer:

| The model writes | Where it goes |
|---|---|
| `@bob: what do you think?` | direct message to bob |
| `@all: heads up` | the room |
| no prefix | wherever the message came from |
| `@skip` | nowhere, the agent stays quiet |

Only the first line is read as a prefix, so an `@name` in the middle of a sentence is just text. An agent that addresses itself is dropped rather than sent.

## The base class

    from chatmesh.drivers import Driver

    class MyDriver(Driver):
        async def handle(self, env: Envelope) -> str | Reply | None:
            return f"got: {env.body}"

Optional lifecycle hooks: `start()` runs once before the first message, `stop()` runs on shutdown.

To wire a driver to an inbox, hand it to `DriverRunner`:

    from chatmesh.drivers import DriverRunner

    runner = DriverRunner(config, MyDriver())
    await runner.run()

The runner subscribes to `agent.inbox.<agent_name>` and `agent.broadcast.>`, drops your own echoes, calls `driver.handle`, and publishes any non-`None` reply on `agent.outbox.<agent_name>` with `reply_to` set to the original `msg_id`.

## The turn cap

Two drivers pointed at each other will keep talking until you stop them, and every turn costs tokens. The runner replies to any one peer at most 50 times, then goes quiet for that peer and logs a warning. Restarting the driver resets the count.

    runner = DriverRunner(config, MyDriver(), max_turns=200)   # raise it
    runner = DriverRunner(config, MyDriver(), max_turns=0)     # no cap

On the CLI it is `--max-turns`. The check runs before `driver.handle`, so a capped peer does not cost an LLM call.

## KimiDriver

Wraps Kimi Code CLI in wire mode. One long-lived process holds the conversation; prompts are JSON-RPC requests over stdin.

    from chatmesh.drivers import KimiDriver

    driver = KimiDriver(
        agent_name="alice",    # used in the chat system prompt
        session="alice",       # kimi --session name
        binary="kimi",         # path if not on PATH
        workdir=None,          # kimi -w
        prompt_timeout=300.0,
        allow_tools=False,     # chat-only by default
        system_prompt=None,    # None uses the built-in chat prompt
        agent_file=None,       # optional: custom Kimi agent YAML
    )

Behavior:

- On `start()`, spawns `kimi --wire --session <name>` and completes the `initialize` handshake.
- Each `handle()` sends a `prompt` request and drains events until a result arrives.
- Mid-flight approval requests from Kimi are auto-approved. Override `_auto_reply_request` if you need policy.
- If a prompt fails (timeout, subprocess died), the driver respawns once and retries.

## ClaudeDriver

Wraps Claude Code CLI. Claude is one-shot per turn, so each `handle()` spawns a fresh process attached to the same session.

    from chatmesh.drivers import ClaudeDriver

    driver = ClaudeDriver(
        agent_name="alice",        # used in the chat system prompt
        session_id=None,           # UUID; auto-generated if omitted
        binary="claude",
        workdir=None,
        model="claude-sonnet-5",   # optional
        skip_permissions=True,     # --dangerously-skip-permissions
        prompt_timeout=300.0,
        allow_tools=False,         # chat-only by default
        bare_mode=True,            # --bare, skip hooks/LSP/plugins
        system_prompt=None,        # None uses the built-in chat prompt
    )

Behavior:

- First turn: `claude -p --session-id <uuid> --input-format stream-json --output-format stream-json ...`.
- Later turns: same command with `-r <uuid>` instead of `--session-id`, which resumes the session.
- Sends one NDJSON user message on stdin, drains NDJSON events on stdout until a `result` event.
- Accumulates text from `assistant` message blocks.
- Errors return a `[claude driver error: ...]` body rather than raising.

Set `skip_permissions=False` if you want Claude Code to prompt for tool permissions. This defeats non-interactive use in most cases.

## Session memory

Both drivers hold conversation memory on the CLI side, keyed by session name (Kimi) or session id (Claude). Same name across restarts means the same conversation continues.

The CLI `chatmesh drive --session NAME` maps a friendly name to both drivers. For Claude, the name is hashed into a stable UUIDv5, so `--session alice` always resolves to the same Claude session id.

## Running from the CLI

    chatmesh drive --config mesh/alice.toml --driver claude
    chatmesh drive --config mesh/bob.toml   --driver kimi

Flags relevant to chat behavior:

- `--allow-tools`: opt in to full agentic mode. Default is chat-only.
- `--system-prompt-file PATH`: use a custom prompt (markdown or plain text).
- `--agent-file PATH`: Kimi only, use a custom Kimi agent YAML.

Ctrl-C to stop.

## Cost warning

Two drivers talking to each other never stop on their own. Every reply costs API tokens. Watch your bill or add an accept filter that limits topics.

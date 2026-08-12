# GUI

A small web dashboard for you (the human) to watch agent traffic and send messages from a browser. Optional. Install with:

    pip install chatmesh[gui]

## Run

    chatmesh gui --config mesh/user.toml

Then open http://127.0.0.1:8765 in a browser.

The GUI represents **you, the human operator**, not an AI agent. It should use a config with an `agent_name` distinct from any driver you are running (e.g. `user`, `me`, or your own name). If you point it at an agent's config by mistake, the AI driver and the GUI will collide on the same inbox and the AIs will start replying to your side of the conversation.

`chatmesh bootstrap` creates `mesh/user.toml` for this reason.

Flags:

- `--host HOST`: bind address. Default `127.0.0.1`. Use `0.0.0.0` to expose on your LAN.
- `--port PORT`: default `8765`.
- `--auth-token TOKEN`: if set, `/send` and `/ws` require `Authorization: Bearer TOKEN` (or `?token=TOKEN` on the WebSocket URL). Leave empty for open dev use.

## What you see

- **Left sidebar:** channels. `broadcast` shows fan-out messages, `all` shows every message, and per-agent DM channels appear as agents show up in the traffic. Under **Between agents** you get one channel per pair of agents talking to each other, so you can follow alice and bob without reading the firehose. Those are read only: it is their conversation, not yours.
- **Feed:** messages in the current channel, code blocks and URLs rendered, priority marked with color.
- **Compose bar:** send a message as the configured identity (usually `user`). Priority selector, textarea, Ctrl-Enter to send.

## Notes

- The GUI does not host a broker. Start NATS separately (`chatmesh bootstrap` does this).
- The GUI does not host a relay. If you want messages routed to inboxes, run `chatmesh relay` too.
- History is in-memory only. Restart clears it.
- Auth token is a shared bearer. Fine for LAN dev; for anything past that, put a real proxy in front with TLS.

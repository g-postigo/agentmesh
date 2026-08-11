# chat

Two AI agents talking to each other over NATS, with the human kicking off the conversation.

alice is driven by Claude Code, bob by Kimi Code. Each spawns its own CLI, listens for messages, and replies. Left running, they hold a conversation. Session memory is per-agent, so restarts pick up where the previous run left off (same `--session` name maps to the same persistent context).

There is a third identity here, `user`. That is you. It exists so the kickoff message has a sender that is not an AI, and so the agents do not include you in the reply loop.

## Requirements

- A running NATS broker on `127.0.0.1:4222`. Start the bundled dev broker:
  `docker compose -f ../../broker/docker-compose.yml up -d`
- Claude Code CLI installed as `claude` on PATH.
- Kimi Code CLI installed as `kimi` on PATH.

## Run

Terminal one, the relay:

    chatmesh relay --config user.toml

Terminal two, alice driven by Claude:

    chatmesh drive --config alice.toml --driver claude

Terminal three, bob driven by Kimi:

    chatmesh drive --config bob.toml --driver kimi

Terminal four, kick off the conversation from the user to bob:

    chatmesh publish --config user.toml --to bob --topic hello \
      "hi bob, please have a short chat with alice: ask her a joke, react, then say chat over"

Both drivers keep replying to each other until you Ctrl-C them.

To watch the traffic in a browser, start the GUI in a fifth terminal:

    chatmesh gui --config user.toml

Then open http://127.0.0.1:8765.

## Notes

- Only one relay per broker is needed. It reads any agent's outbox, so any config works for `chatmesh relay`.
- Session memory lives inside Kimi and Claude, keyed by session id. Wipe it by choosing a new `--session` value or deleting the CLI's session store.
- Cost of leaving two AI agents chatting is real. Watch your API bills.

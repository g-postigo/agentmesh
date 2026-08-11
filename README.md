# chatmesh

Python library to connect multiple long-running agents over NATS JetStream.

Ships a message envelope, a listener that survives crashes, a publisher, a watcher process, and adapters for Kimi Code CLI and Claude Code CLI.

Extracted from a personal setup with four agents on two hosts, so the shape reflects what actually runs.

## Quickstart

If you don't want to read anything, open [AGENT_PROMPT.md](AGENT_PROMPT.md), paste the whole thing into ChatGPT, Claude, or Kimi, and let it set everything up for you.

If you'd rather do it yourself:

    git clone https://github.com/g-postigo/chatmesh.git
    cd chatmesh
    pip install -e ".[dev]"
    chatmesh bootstrap

Follow the commands `bootstrap` prints.

## Status

v1.0. The API is frozen. Envelope, publisher, listener, sidecar, watcher, relay, CLI, Kimi + Claude Code drivers, web GUI, and one-command bootstrap all in.

## Docs

- [Getting started](docs/getting-started.md)
- [CLI reference](docs/cli.md)
- [Envelope format](docs/envelope.md)
- [Drivers](docs/drivers.md)
- [Relay](docs/relay.md)
- [GUI](docs/gui.md)
- [Local broker](docs/broker-local.md)
- [Production broker](docs/broker-production.md)
- [Security notes](docs/security.md)

## License

MIT.

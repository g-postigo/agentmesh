# chatmesh

[![ci](https://github.com/g-postigo/chatmesh/actions/workflows/ci.yml/badge.svg)](https://github.com/g-postigo/chatmesh/actions/workflows/ci.yml)
[![pypi](https://img.shields.io/pypi/v/chatmesh)](https://pypi.org/project/chatmesh/)
[![python](https://img.shields.io/pypi/pyversions/chatmesh)](https://pypi.org/project/chatmesh/)
[![license](https://img.shields.io/pypi/l/chatmesh)](LICENSE)

Put your AI coding agents in a chat room together.

chatmesh runs Claude Code and Kimi Code as long-lived processes on a NATS bus. They see each other's messages, answer the room or each other privately, and stay quiet when they have nothing to add. You watch it happen in a browser and join in.

## What it looks like

You type in the broadcast channel. Every agent gets it, and each one decides what to do about it.

    you       #standup   what is left before we ship?
    alice     #standup   the retry path is untested. bob owns that file.
    bob       @alice     sending you the branch, it is green locally
    bob       #standup   tests are up, nothing else blocking from my side

`alice` answered the room. `bob` sent alice a direct message and then reported back to the room. Nobody was told to do that in code. The agents pick where their answer goes.

## Quickstart

You need Docker and either the Claude Code CLI or the Kimi Code CLI on your PATH.

    git clone https://github.com/g-postigo/chatmesh.git
    cd chatmesh
    pip install -e ".[dev]"
    chatmesh bootstrap

`bootstrap` writes the config files, starts a local NATS broker, and prints the four commands to run. Open `http://127.0.0.1:8765` and talk to them.

If you would rather not read any of this, paste [AGENT_PROMPT.md](AGENT_PROMPT.md) into ChatGPT, Claude, or Kimi and let it do the setup.

Already have a broker and just want the library: `pip install chatmesh`. The `bootstrap` command is the only part that needs the cloned repo, since it reaches for `broker/docker-compose.yml`.

## How an agent decides where to answer

By default a reply goes back where the message came from: the room for a broadcast, the sender for a direct message. An agent overrides that by starting its answer with a prefix.

| The agent writes | Where it goes |
|---|---|
| `@bob: what do you think?` | direct message to bob |
| `@all: heads up` | the room |
| no prefix | wherever the message came from |
| `@skip` | nowhere, it stays quiet |

Every prompt an agent receives opens with the channel, the sender, the topic, and who else is present, so it can tell a task meant for it from a discussion it is only overhearing.

## Writing your own agent

The AI adapters are not special. A driver is any class that turns a message into an answer.

```python
import asyncio

from chatmesh import Config
from chatmesh.drivers import Driver, DriverRunner, Reply


class Triage(Driver):
    async def handle(self, env):
        if "deploy" not in env.body:
            return None  # stay quiet
        if env.to == "broadcast":
            return "holding deploys until CI is green"
        return Reply("asking bob to confirm", to="bob")


runner = DriverRunner(Config.load("alice.toml"), Triage())
asyncio.run(runner.run())
```

## What is in the box

- **Envelope**: one JSON message format, versioned, with sender, recipient, topic, priority and TTL.
- **Publisher and listener**: send and receive, with a JSONL sidecar that survives restarts and skips duplicates.
- **Relay**: routes outboxes to inboxes and to the broadcast channel. Run a second one and they share the load.
- **Watcher**: keeps a process alive, and actually stops when you stop it.
- **Drivers**: Claude Code and Kimi Code, both in chat mode with every tool disabled by default.
- **GUI**: a small web chat with a broadcast channel, per agent DMs, and an observer view of every message on the bus.
- **CLI**: `bootstrap`, `listen`, `publish`, `relay`, `drive`, `watch`, `gui`.

## Delivery, honestly

By default messages go over core NATS, which is at-most-once. If an agent is not listening when a message is sent, that message is gone.

Put `durable = true` in an agent's config and it publishes into a JetStream stream and reads from a durable consumer instead, so whatever arrived while it was down is waiting when it comes back. The cost is at-least-once delivery, which the runner and the sidecar both deduplicate. See [docs/durable.md](docs/durable.md).

Two agents pointed at each other will keep talking. Each one stops after 50 replies to the same peer, which you can change with `--max-turns`. Agents also decide on their own when to stay quiet, but that is a judgement call by a language model, not a guarantee.

Chat mode blocks every tool the CLIs ship. `--allow-tools` turns them back on, and at that point you are running an autonomous agent with shell access and no human approving anything. Read [docs/security.md](docs/security.md) before you do that.

## Where this came from

Extracted from a personal setup running four agents across two hosts. The shape reflects what actually ran, not what looked good on a diagram.

## Docs

- [Getting started](docs/getting-started.md)
- [CLI reference](docs/cli.md)
- [Envelope format](docs/envelope.md)
- [Drivers and the room](docs/drivers.md)
- [Durable delivery](docs/durable.md)
- [Relay](docs/relay.md)
- [GUI](docs/gui.md)
- [Local broker](docs/broker-local.md)
- [Production broker](docs/broker-production.md)
- [Security notes](docs/security.md)

## Status

v1.2. Python 3.11 through 3.14, tested on Linux, macOS and Windows. The API is frozen; 1.1 and 1.2 only added keyword arguments and one config key.

MIT licensed.

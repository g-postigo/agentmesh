# Getting started

## Install

    pip install chatmesh

Requires Python 3.11 or newer.

## Start a local broker

Docker Compose config lives in `broker/`. From a clone of this repo:

    docker compose -f broker/docker-compose.yml up -d

That gives you NATS on `nats://127.0.0.1:4222` with JetStream enabled.

## One-command setup

    chatmesh bootstrap

That creates three configs under `mesh/` (`alice.toml`, `bob.toml`, `user.toml`), starts the broker, and prints the next commands to run.

`alice` and `bob` are AI agents. `user` is you, the human. The GUI and any manual `chatmesh publish` command run as `user` so nothing collides with the AI drivers.

## Two agents, one message

Terminal one, run bob's listener:

    chatmesh listen --config mesh/bob.toml

Terminal two, publish from the user:

    chatmesh publish --config mesh/user.toml --to bob --topic greet "hello bob"

The envelope lands in `mesh/bob.jsonl`, one line per message.

See [cli.md](cli.md) for every flag and [envelope.md](envelope.md) for the wire format.

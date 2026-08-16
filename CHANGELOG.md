# Changelog

## 1.3

### You can try it without an LLM

`chatmesh drive --driver echo` runs an agent with no model behind it. It answers
direct messages and speaks on the broadcast channel only when its name comes up.

Until now the first run needed the Claude Code or Kimi Code CLI installed and
logged in, which is a lot to ask of someone who just wants to see whether the
thing works. It is also the fastest way to tell a broken broker from a broken
model.

### Fixed

- Two durable delivery tests were passing for the wrong reason. Publishers write
  to `agent.outbox.<from>` and listeners read `agent.inbox.<name>`, so with no
  relay between them nothing was being routed at all. A stray relay left running
  on the development machine was making them green. Both now run their own
  relay, and the core NATS control case is a real comparison instead of an empty
  list matching an empty list.

## 1.2

### Messages can survive an agent being down

Core NATS is at-most-once, so a message sent while an agent was restarting was
gone. That sat badly next to a watcher whose whole job is restarting agents.

Put `durable = true` in an agent's config and it publishes into a JetStream
stream and reads from a durable consumer, so whatever arrived during the
downtime is waiting for it. Off by default, and it can be turned on one process
at a time, since a durable publisher still reaches core subscribers. See
[docs/durable.md](docs/durable.md).

A new agent starts from the moment it first connects, not from the beginning of
the stream, so joining an old mesh does not hand an LLM a day of backlog to
answer.

### Fixed

- The GUI broadcast channel was always empty. It filtered on the subject, but
  the same message arrives from both the sender's outbox and the relay, and the
  outbox copy wins, so the stored subject was never the broadcast one.
- Anything published by the GUI's own agent from the CLI never appeared in the
  GUI at all.

### Also

- The GUI has a channel per pair of agents talking to each other, read only.
- The driver runner deduplicates by message id.
- The stream parsers in both AI drivers finally have tests.
- `python -m chatmesh` works, not just the console script.
- GUI tokens are compared in constant time.
- `priority` and `ttl_seconds` are documented as advisory, which is what they
  have always been. Nothing in chatmesh orders or expires by them.

## 1.1

### Agents talk in a room, not in pairs

An agent used to answer whoever spoke to it, always privately, always with
`topic="reply"`. It could not address another agent and could not tell a
broadcast from a message meant for it alone.

Now a reply goes back where the message came from, the room for a broadcast and
the sender for a direct message, carrying the original topic so a thread stays
one thread. A driver overrides that by returning `Reply(body, to=..., topic=...)`.
The LLM drivers get there from plain text: the model starts its answer with
`@bob:` for a direct message, `@all:` for the room, or `@skip` to say nothing.

Each agent also sees who is present. Prompts now open with the channel, the
sender, the topic, and the roster. The roster comes from an optional `peers` key
in the config and grows as names show up in traffic.

### Heads up

`chatmesh drive` now stops replying to a peer after 50 replies. Two drivers
pointed at each other used to talk until you killed them, and every turn costs
tokens. Pass `--max-turns 0` to get the old behaviour back, or a bigger number
to move the ceiling.

### Fixed

- `chatmesh watch` ignored SIGTERM until the child process happened to exit on
  its own, so it never stopped under a service manager. It now terminates the
  child, waits out a grace period, and kills it if it is still there.
- The relay subscribed without a queue group, so a second relay duplicated
  every message. Relays now share a queue group and split the traffic.
- The GUI built its own copy of the envelope by hand and stamped a different
  timestamp format than the rest of the library. It uses `Envelope` now, and a
  bad priority gets a 400 instead of going out on the wire.
- The sidecar read the whole file on startup to warm its dedup window. It reads
  backwards from the end instead, which matters once an agent has been running
  for a few weeks.
- Shutting the GUI down raised `CancelledError`, because `suppress(Exception)`
  does not catch it.
- The GUI checked the broker connection before validating the request, so a
  malformed send was only rejected when the broker happened to be up.

### Housekeeping

- Ship `py.typed`, so type checkers pick up the annotations that were already there.
- Version lives in one place (`chatmesh.__version__`) and the build reads it from there.
- Top-level exports: `Config`, `Publisher`, `Listener`, `Sidecar`, `Relay`, `Watcher`, and the error types are importable straight from `chatmesh`.
- Renamed `AgentmeshError` to `ChatmeshError`. The old name still works.
- Dropped the JetStream claim from the README and the package description. The library talks core NATS.
- Test on Python 3.14 in CI, and advertise it.

## 1.0

First release.

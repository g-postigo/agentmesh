# Changelog

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

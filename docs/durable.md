# Durable delivery

By default chatmesh talks core NATS, which is at-most-once. If nobody is
listening on a subject when a message is published, that message is gone. For a
demo on one machine that is fine. For a mesh where the watcher restarts crashed
agents it is not: every restart is a window where messages disappear.

Turn it on per agent:

    durable = true

That is all the config there is. The agent now publishes into a JetStream
stream and consumes from it with a durable consumer, so anything that arrived
while it was down is waiting when it comes back.

## What it changes

| | Core NATS (default) | `durable = true` |
|---|---|---|
| Sent while the agent is down | lost | delivered when it returns |
| Delivery count | at most once | at least once |
| Broker restart | messages lost | messages survive, they are on disk |
| Publish call | fire and forget | waits for the stream to ack |

At-least-once is the price. The same message can arrive twice, so the driver
runner remembers the last 500 message ids and drops a repeat, and the sidecar
already deduplicates by `msg_id`.

## Turning it on gradually

Publishing durably and consuming durably are separate choices, and a durable
publisher still reaches plain core subscribers. So you can flip one agent at a
time and the mesh keeps working throughout. The one to flip first is the relay:
it is the only thing moving outboxes to inboxes, so a message sent while it is
down is lost no matter what the agents are configured to do.

## The stream

First component to connect creates it, and the rest reuse it.

- Name: `CHATMESH`
- Subjects: `agent.>`
- Retention: limits, 24 hours or 100,000 messages, whichever comes first

Consumers are named after the role and the agent: `inbox-alice`,
`broadcast-alice`, `driver-inbox-alice`, `relay`. Inspect them with the usual
tooling:

    nats stream info CHATMESH
    nats consumer ls CHATMESH

## A new agent does not get the backlog

A durable consumer is created the first time an agent starts, and it starts from
that moment, not from the beginning of the stream. Joining a mesh that has been
running all day does not hand you a day of conversation to answer, which for an
LLM driver would be a large bill and a very confused first message. Once the
consumer exists it resumes from the last message it acknowledged, which is the
point of the whole thing.

## When the acknowledgement happens

- **Listener:** after the envelope is on disk in the sidecar. A crash before
  that replays the message.
- **Relay:** after the forwarded copy is in the stream.
- **Driver runner:** on receipt, before the model is called. A turn can run for
  minutes, and holding the acknowledgement open that long invites a redelivery
  on top of the turn already in flight. The trade is that a crash in the middle
  of a turn loses that one message, the same as core NATS. Everything queued
  while the process was down still arrives.

A message whose envelope will not parse is terminated rather than acknowledged,
so it stops being redelivered instead of blocking the consumer forever.

## What this does not do

The GUI still subscribes over core NATS. It is a viewer with its own scrollback,
and giving it a durable consumer would mean replaying old traffic into the
browser on every restart.

`ttl_seconds` on the envelope is still not enforced. Stream retention is what
actually expires a message.

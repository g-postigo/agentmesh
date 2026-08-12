# Envelope

The single message type on the wire. JSON on NATS, one dict per message.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `msg_id` | string | Unique id for this message. UUIDv4. Used for dedup on the receiver side. |
| `from` | string | Sender agent name. |
| `to` | string | Recipient agent name, or `"broadcast"` for fan-out. |
| `reply_to` | string or null | `msg_id` this envelope is a reply to, or null. |
| `ts` | string | ISO 8601 UTC timestamp with trailing `Z`, seconds precision. |
| `topic` | string | Short label for what this message is about. Free-form. |
| `priority` | string | One of `low`, `normal`, `high`, `urgent`. Advisory. |
| `ttl_seconds` | integer | Non-negative. Advisory. |
| `body` | string | Opaque payload. Agents agree on the encoding. |
| `version` | integer | Envelope schema version. Currently `1`. |

## Wire example

    {
      "msg_id": "1b7e4bfe-3b1b-4b2b-9f4a-8a2d1b6a8a3c",
      "from": "alice",
      "to": "bob",
      "reply_to": null,
      "ts": "2026-08-10T14:32:11Z",
      "topic": "greet",
      "priority": "normal",
      "ttl_seconds": 3600,
      "body": "hello bob",
      "version": 1
    }

## Python

    from chatmesh import Envelope

    env = Envelope.new(
        from_="alice",
        to="bob",
        topic="greet",
        body="hello bob",
    )
    wire = env.to_json()
    back = Envelope.from_json(wire)

The field is `from_` in Python because `from` is a keyword. On the wire it is plain `from`. The mapping happens in `to_json` and `from_json`.

## Subjects

Publishers write to `agent.outbox.<from>`. Listeners subscribe to `agent.inbox.<agent_name>` and `agent.broadcast.>`.

To bridge the two, run `chatmesh relay --config <any-agent>.toml`. It reads `agent.outbox.>` and republishes each envelope on `agent.inbox.<to>` (or `agent.broadcast.<topic>.<from>` for broadcasts). One relay per broker. See [relay.md](relay.md).

## Advisory fields

`priority` and `ttl_seconds` are carried and validated, and nothing in chatmesh
acts on them. The runner's queue is first in, first out, and no component
expires a message. They are there so your own driver, or a dashboard, can read
them and decide something. What actually expires a message is the stream
retention when [durable delivery](durable.md) is on.

Do not read a `priority` of `urgent` as a promise that it will be handled first.

## Version bumps

Any change that breaks the field set or their semantics bumps `version`. Old readers reject envelopes with a version they do not know.

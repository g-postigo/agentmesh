# Relay

Publishers write to `agent.outbox.<from>`. Listeners subscribe to `agent.inbox.<to>` and `agent.broadcast.>`. Nothing bridges the two by default; the relay does.

## Command

    chatmesh relay --config any-agent.toml

Any config works, since the relay only needs the broker URL and connection material. Run one relay per broker.

## Routing

For each message received on `agent.outbox.>`:

- If `env.to == "broadcast"`, forward to `agent.broadcast.<topic>.<from>`.
- Otherwise, forward to `agent.inbox.<env.to>`.

Malformed envelopes are dropped silently.

## Why a separate process

- The broker itself does not know about agent names or the envelope schema.
- Keeping routing outside the broker means one NATS config works across projects with different agent conventions.
- The relay is stateless. Restart it any time.

## Alternatives

- Publish directly to `agent.inbox.<to>` from your app and skip the relay. Fine for smoke tests. Loses the "sender named themselves" audit trail that the outbox pattern gives.
- Roll a bigger relay that does signing, rate limiting, or per-agent filtering. `chatmesh relay` is deliberately small so you can replace it.

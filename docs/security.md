# Security

What chatmesh assumes and what it does not.

## Assumes

- The NATS broker you point at is trusted. Anyone who can reach the broker can subscribe to and publish on the same subjects your agents use.
- Config files on disk are trusted. They can name arbitrary broker URLs, arbitrary file paths, and arbitrary nkey seed files. Guard them like you would any credential file.
- The environment running the agent is trusted. chatmesh does not sandbox anything.

## Does not check

- **No message signing.** chatmesh does not sign envelopes. If you need message-level authenticity beyond the transport, sign the `body` yourself before publishing and verify on receive.
- **No sender verification.** The `from` field in an envelope is whatever the sender put there. NATS accounts and nkeys constrain who can publish where, but chatmesh does not cross-check the wire `from` against the connection identity.
- **No encryption of the body.** The body is opaque text on the wire. If your broker is not on TLS, treat everything as plaintext.
- **No replay protection across restarts.** The dedup ring is in-memory plus a warm-up from the tail of the sidecar file. Old messages beyond the tail window will be re-accepted if replayed.
- **No rate limiting.** A hostile publisher can flood a listener.
- **No file permission enforcement.** The sidecar and log files are written with your process's umask.

## What you probably want in production

- Run NATS with TLS.
- Use nkey accounts, one per agent, with subject permissions that match the topic model.
- Put the sidecar and log files in a directory only your agent user can read.
- If your body is sensitive, sign it or encrypt it at the application layer. Do not rely on the broker to be the trust boundary.

For a production deployment, see [broker-production.md](broker-production.md).

# Local broker

For development. Not for production.

## Start

    docker compose -f broker/docker-compose.yml up -d

That runs `nats:2.10-alpine` on `127.0.0.1:4222` with JetStream on and no auth. Config in `broker/nats-server.conf`.

## Stop

    docker compose -f broker/docker-compose.yml down

Add `-v` to also drop the data volume.

## Health check

The monitoring endpoint is on `http://127.0.0.1:8222`.

    curl http://127.0.0.1:8222/varz | head

## Notes

- No authentication. Anything on your machine can publish and subscribe.
- No TLS. Plaintext WebSocket / TCP.
- JetStream data lives in a Docker volume named `chatmesh_nats-data`.
- For production (auth, TLS, nkeys, real retention), see [broker-production.md](broker-production.md).

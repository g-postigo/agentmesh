# Production broker

The Docker Compose broker in `broker/` is for local development only. No auth, no TLS, one node. Real deployments need at least the four things below.

## TLS

Give the broker a certificate and require TLS from every client. Sample block:

    tls {
      cert_file: "/etc/nats/tls/server.crt"
      key_file:  "/etc/nats/tls/server.key"
      ca_file:   "/etc/nats/tls/ca.crt"
      verify:    true
    }

On the client side, point `chatmesh` at the CA and give it a client cert if you want mutual TLS.

## nkey accounts, one per agent

Each agent gets its own nkey seed. The broker only accepts publishes to `agent.outbox.<name>` from the account whose key matches, and only accepts subscribes to `agent.inbox.<name>` and `agent.broadcast.>` on the same account.

Skeleton `nats-server.conf`:

    accounts {
      alice: {
        users: [{ nkey: UAAAAAAAAA...alice }]
        exports: [
          { stream: "agent.outbox.alice" }
        ]
      }
      bob: {
        users: [{ nkey: UBBBBBBBBB...bob }]
        exports: [
          { stream: "agent.outbox.bob" }
        ]
      }
      relay: {
        users: [{ nkey: URRRR...relay }]
        imports: [
          { stream: { account: "alice", subject: "agent.outbox.alice" } }
          { stream: { account: "bob",   subject: "agent.outbox.bob" } }
        ]
      }
    }

Mint keys with `nk`:

    nk -gen user -pubout > alice.pub
    nk -gen user > alice.nk

Store the seed file on the agent host, referenced from its `nkey_seed_path` in the TOML config.

## JetStream retention

Configure the `AGENTS` stream with the retention your ops model needs:

    jetstream {
      store_dir: "/var/lib/nats"
      max_memory_store: 1GB
      max_file_store:   50GB
    }

Stream definition, applied with `nats stream add`:

    {
      "name": "AGENTS",
      "subjects": ["agent.inbox.*", "agent.broadcast.>"],
      "retention": "limits",
      "max_age": 259200000000000,   // 3 days
      "storage": "file",
      "num_replicas": 1
    }

Three days is what noctus uses. Adjust to taste.

## Systemd

    [Unit]
    Description=NATS server
    After=network-online.target

    [Service]
    Type=simple
    User=nats
    ExecStart=/usr/local/bin/nats-server -c /etc/nats/nats-server.conf
    Restart=on-failure
    RestartSec=2s
    LimitNOFILE=1000000

    [Install]
    WantedBy=multi-user.target

## Firewalling

Bind the broker to the interface the agents actually reach. NATS on 4222 is unauthenticated in the wrong config; make sure the port is not open to the public internet.

## Backups

JetStream data is on-disk in `store_dir`. Snapshot the directory on your usual backup schedule. Restore is put-files-back-then-restart.

## What chatmesh does not check

chatmesh trusts the broker you point it at. If the broker is misconfigured, chatmesh will happily publish to and subscribe from whatever it can reach. See [security.md](security.md).

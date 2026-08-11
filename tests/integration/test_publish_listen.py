"""End-to-end: publisher sends, listener receives, sidecar records.

Requires a running NATS broker on nats://127.0.0.1:4222.
Skipped automatically if no broker is reachable.

Start the dev broker with:  docker compose -f broker/docker-compose.yml up -d
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from pathlib import Path

import pytest

from chatmesh import Envelope
from chatmesh.config import Config
from chatmesh.listener import Listener
from chatmesh.publisher import Publisher
from chatmesh.sidecar import Sidecar

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 4222


def _broker_up() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=0.3):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _broker_up(), reason="no NATS broker on 127.0.0.1:4222")


def _make_config(tmp_path: Path, name: str) -> Config:
    return Config(
        broker_url=f"nats://{BROKER_HOST}:{BROKER_PORT}",
        agent_name=name,
        sidecar_path=tmp_path / f"{name}.jsonl",
        log_path=tmp_path / f"{name}.log",
    )


@pytest.mark.asyncio
async def test_publish_lands_in_sidecar(tmp_path: Path) -> None:
    bob_cfg = _make_config(tmp_path, "bob")
    bob_sidecar = Sidecar(bob_cfg.sidecar_path)
    listener = Listener(bob_cfg, bob_sidecar)
    listen_task = asyncio.create_task(listener.run())
    await asyncio.sleep(0.2)  # give the subscription a moment to register

    alice_cfg = _make_config(tmp_path, "alice")
    pub = Publisher(alice_cfg)
    await pub.connect()
    env = Envelope.new("alice", "bob", "greet", "hello")
    # Direct-to-bob goes on agent.inbox.bob, not the outbox namespace.
    # The publisher writes to agent.outbox.<from>, so bob will not see it
    # unless we simulate the relay. For this smoke test, publish to inbox
    # directly using the underlying nats client.
    await pub._nc.publish(f"agent.inbox.{env.to}", env.to_json())  # type: ignore[union-attr]
    await pub._nc.flush()  # type: ignore[union-attr]
    await pub.close()

    await asyncio.sleep(0.3)
    listen_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listen_task

    assert bob_sidecar.has_seen(env.msg_id)

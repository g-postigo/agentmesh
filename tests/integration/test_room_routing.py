"""End-to-end: a broadcast reaches every agent, and replies land where the
agent aimed them.

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
from chatmesh.drivers import Driver, DriverRunner, Reply
from chatmesh.publisher import Publisher
from chatmesh.relay import Relay

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 4222


def _broker_up() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=0.3):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _broker_up(), reason="no NATS broker on 127.0.0.1:4222")


def _config(tmp_path: Path, name: str) -> Config:
    return Config(
        broker_url=f"nats://{BROKER_HOST}:{BROKER_PORT}",
        agent_name=name,
        sidecar_path=tmp_path / f"{name}.jsonl",
        log_path=tmp_path / f"{name}.log",
    )


class _Scripted(Driver):
    """Records what it was handed and answers with a canned reply."""

    def __init__(self, reply: str | Reply | None) -> None:
        self.reply = reply
        self.seen: list[Envelope] = []

    async def handle(self, env: Envelope) -> str | Reply | None:
        self.seen.append(env)
        return self.reply


@contextlib.asynccontextmanager
async def _running(*coros):
    tasks = [asyncio.create_task(c) for c in coros]
    try:
        # Give the subscriptions a moment to land before anyone publishes.
        await asyncio.sleep(0.4)
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _publish(cfg: Config, env: Envelope) -> None:
    pub = Publisher(cfg)
    await pub.connect()
    await pub.publish(env)
    await pub.close()


async def _wait_for(check, timeout: float = 6.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if check():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timed out waiting for the mesh")


async def test_broadcast_reaches_both_agents_and_replies_land_in_the_room(tmp_path: Path):
    user = _config(tmp_path, "user")
    alice_cfg = _config(tmp_path, "alice")
    bob_cfg = _config(tmp_path, "bob")

    alice = _Scripted("alice here")
    # bob stays quiet, otherwise the two of them answer each other's replies
    # for the length of the test.
    bob = _Scripted(None)

    async with _running(
        Relay(user).run(),
        DriverRunner(alice_cfg, alice).run(),
        DriverRunner(bob_cfg, bob).run(),
    ):
        await _publish(user, Envelope.new("user", "broadcast", "standup", "status?"))
        await _wait_for(lambda: alice.seen and bob.seen)
        # bob has to see alice's answer too, or it was not a room reply.
        await _wait_for(lambda: len(bob.seen) >= 2)

    assert alice.seen[0].body == "status?"
    assert bob.seen[0].body == "status?"
    from_alice = [e for e in bob.seen if e.from_ == "alice"]
    assert from_alice, "bob never saw alice's reply"
    assert from_alice[0].to == "broadcast"
    assert from_alice[0].topic == "standup"


async def test_an_agent_can_direct_message_a_peer(tmp_path: Path):
    user = _config(tmp_path, "user")
    alice_cfg = _config(tmp_path, "alice")
    bob_cfg = _config(tmp_path, "bob")

    alice = _Scripted(Reply("just between us", to="bob"))
    bob = _Scripted(None)

    async with _running(
        Relay(user).run(),
        DriverRunner(alice_cfg, alice).run(),
        DriverRunner(bob_cfg, bob).run(),
    ):
        await _publish(user, Envelope.new("user", "alice", "task", "ask bob"))
        await _wait_for(lambda: any(e.from_ == "alice" for e in bob.seen))

    dm = next(e for e in bob.seen if e.from_ == "alice")
    assert dm.to == "bob"
    assert dm.body == "just between us"


async def test_a_quiet_agent_sends_nothing(tmp_path: Path):
    user = _config(tmp_path, "user")
    alice_cfg = _config(tmp_path, "alice")
    bob_cfg = _config(tmp_path, "bob")

    alice = _Scripted(None)
    bob = _Scripted(None)

    async with _running(
        Relay(user).run(),
        DriverRunner(alice_cfg, alice).run(),
        DriverRunner(bob_cfg, bob).run(),
    ):
        await _publish(user, Envelope.new("user", "broadcast", "standup", "status?"))
        await _wait_for(lambda: alice.seen and bob.seen)
        await asyncio.sleep(0.5)

    assert len(alice.seen) == 1
    assert len(bob.seen) == 1

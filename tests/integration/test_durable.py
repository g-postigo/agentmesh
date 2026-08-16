"""End-to-end: a message sent while an agent is down is waiting for it.

This is the entire reason durable delivery exists. On core NATS every one
of these messages would be gone.

Requires a running NATS broker on nats://127.0.0.1:4222.
Start it with:  docker compose -f broker/docker-compose.yml up -d
"""

from __future__ import annotations

import asyncio
import socket
import uuid
from pathlib import Path

import pytest

from chatmesh import Envelope
from chatmesh.config import Config
from chatmesh.drivers import Driver, DriverRunner, Reply
from chatmesh.publisher import Publisher
from chatmesh.relay import Relay
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


def _cfg(tmp_path: Path, name: str, *, durable: bool = True) -> Config:
    return Config(
        broker_url=f"nats://{BROKER_HOST}:{BROKER_PORT}",
        agent_name=name,
        sidecar_path=tmp_path / f"{name}.jsonl",
        log_path=tmp_path / f"{name}.log",
        durable=durable,
    )


def _unique(prefix: str) -> str:
    """Fresh name per run, so durables from earlier runs stay out of the way."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _run_briefly(coro, seconds: float) -> None:
    """Start something that runs forever, let it settle, then stop it."""
    task = asyncio.create_task(coro)
    await asyncio.sleep(seconds)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _publish(cfg: Config, env: Envelope) -> None:
    pub = Publisher(cfg)
    await pub.connect()
    await pub.publish(env)
    await pub.close()


async def _missed_messages(tmp_path: Path, *, durable: bool) -> list[str]:
    """Send three messages to an agent that is down, then bring it back.

    A relay has to be up throughout: publishers write to
    `agent.outbox.<from>` and listeners read `agent.inbox.<name>`, so
    without one nothing connects the two and the result would be empty
    whatever the delivery guarantees are.
    """
    from chatmesh.listener import Listener

    name = _unique("bob")
    cfg = _cfg(tmp_path, name, durable=durable)
    sender = _cfg(tmp_path, _unique("user"), durable=durable)
    relay = asyncio.create_task(Relay(_cfg(tmp_path, _unique("relay"), durable=durable)).run())
    try:
        await asyncio.sleep(0.5)
        # First run is what creates the durable consumer.
        await _run_briefly(Listener(cfg, Sidecar(cfg.sidecar_path)).run(), 1.2)

        # Down. Three messages are sent to it anyway.
        for i in range(3):
            await _publish(sender, Envelope.new(sender.agent_name, name, "work", f"missed {i}"))
        await asyncio.sleep(0.6)
        assert not cfg.sidecar_path.exists() or cfg.sidecar_path.read_text() == ""

        # Back up.
        await _run_briefly(Listener(cfg, Sidecar(cfg.sidecar_path)).run(), 2.5)
    finally:
        relay.cancel()
        await asyncio.gather(relay, return_exceptions=True)

    # Filter to our own sender: the stream carries `agent.>`, so on a shared
    # broker other traffic reaches the broadcast subscription too.
    return [e.body for e in Sidecar(cfg.sidecar_path).read_new() if e.from_ == sender.agent_name]


async def test_listener_gets_what_arrived_while_it_was_down(tmp_path: Path):
    assert await _missed_messages(tmp_path, durable=True) == ["missed 0", "missed 1", "missed 2"]


async def test_core_nats_loses_the_same_messages(tmp_path: Path):
    """The control case, so the test above is measuring something.

    Same relay, same timing, same everything except the flag.
    """
    assert await _missed_messages(tmp_path, durable=False) == []


class _Echo(Driver):
    def __init__(self) -> None:
        self.seen: list[Envelope] = []

    async def handle(self, env: Envelope) -> Reply | None:
        self.seen.append(env)
        return Reply("ack: " + env.body, to=env.from_)


async def test_a_driver_answers_a_message_queued_while_it_was_offline(tmp_path: Path):
    alice = _unique("alice")
    alice_cfg = _cfg(tmp_path, alice)
    relay_cfg = _cfg(tmp_path, _unique("relay"))
    user_cfg = _cfg(tmp_path, _unique("user"))

    driver = _Echo()

    def ours() -> list[str]:
        # The stream carries every `agent.>` subject, so on a shared broker
        # alice's broadcast subscription picks up other tests too.
        return [e.body for e in driver.seen if e.from_ == user_cfg.agent_name]

    # First run creates alice's durable consumers.
    await _run_briefly(DriverRunner(alice_cfg, driver).run(), 1.2)
    assert ours() == []

    # alice is offline. The relay is up and routes the message to her inbox,
    # where it sits in the stream.
    relay = asyncio.create_task(Relay(relay_cfg).run())
    await asyncio.sleep(0.5)
    await _publish(user_cfg, Envelope.new(user_cfg.agent_name, alice, "work", "still there?"))
    await asyncio.sleep(0.8)

    # alice comes back.
    await _run_briefly(DriverRunner(alice_cfg, driver).run(), 2.0)
    relay.cancel()
    await asyncio.gather(relay, return_exceptions=True)

    assert ours() == ["still there?"]


async def test_a_redelivered_message_is_answered_once(tmp_path: Path):
    """At-least-once means the same message can show up twice."""
    alice_cfg = _cfg(tmp_path, _unique("alice"))
    runner = DriverRunner(alice_cfg, _Echo())
    env = Envelope.new("user", alice_cfg.agent_name, "work", "hello")

    class _Msg:
        data = env.to_json()

        async def ack(self) -> None:
            return None

    await runner._on_durable_msg(_Msg())  # type: ignore[arg-type]
    await runner._on_durable_msg(_Msg())  # type: ignore[arg-type]

    assert runner._queue.qsize() == 1

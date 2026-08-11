from __future__ import annotations

from pathlib import Path

from chatmesh import Envelope
from chatmesh.config import Config
from chatmesh.relay import Relay


class _FakeNats:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.published.append((subject, payload))


def _cfg() -> Config:
    return Config(
        broker_url="nats://127.0.0.1:4222",
        agent_name="relay",
        sidecar_path=Path("."),
        log_path=Path("."),
    )


class _Msg:
    def __init__(self, data: bytes) -> None:
        self.data = data


async def test_forward_direct_message_to_inbox():
    r = Relay(_cfg())
    r._nc = _FakeNats()  # type: ignore[assignment]
    env = Envelope.new("alice", "bob", "greet", "hi")
    await r._forward(_Msg(env.to_json()))
    subjects = [s for s, _ in r._nc.published]  # type: ignore[attr-defined]
    assert subjects == ["agent.inbox.bob"]


async def test_forward_broadcast_uses_topic_and_from():
    r = Relay(_cfg())
    r._nc = _FakeNats()  # type: ignore[assignment]
    env = Envelope.new("alice", "broadcast", "status", "online")
    await r._forward(_Msg(env.to_json()))
    subjects = [s for s, _ in r._nc.published]  # type: ignore[attr-defined]
    assert subjects == ["agent.broadcast.status.alice"]


async def test_forward_ignores_bad_envelope():
    r = Relay(_cfg())
    r._nc = _FakeNats()  # type: ignore[assignment]
    await r._forward(_Msg(b"not json"))
    assert r._nc.published == []  # type: ignore[attr-defined]

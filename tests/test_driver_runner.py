from __future__ import annotations

from pathlib import Path

from chatmesh import Envelope
from chatmesh.config import Config
from chatmesh.drivers import Driver, DriverRunner, Reply


class _Fixed(Driver):
    def __init__(self, reply: str | Reply | None) -> None:
        self._reply = reply

    async def handle(self, env: Envelope) -> str | Reply | None:
        return self._reply


class _Counting(Driver):
    def __init__(self) -> None:
        self.calls = 0

    async def handle(self, env: Envelope) -> str | None:
        self.calls += 1
        return f"echo: {env.body}"


class _FakePub:
    def __init__(self) -> None:
        self.sent: list[Envelope] = []

    async def publish(self, env: Envelope) -> None:
        self.sent.append(env)


def _cfg() -> Config:
    return Config(
        broker_url="nats://127.0.0.1:4222",
        agent_name="alice",
        sidecar_path=Path("."),
        log_path=Path("."),
    )


def _from(peer: str) -> Envelope:
    return Envelope.new(peer, "alice", "t", "hi")


async def _feed(runner: DriverRunner, pub: _FakePub, peer: str, times: int) -> None:
    for _ in range(times):
        await runner._handle_one(_from(peer), pub)  # type: ignore[arg-type]


async def test_stops_replying_after_max_turns():
    driver = _Counting()
    runner = DriverRunner(_cfg(), driver, max_turns=3)
    pub = _FakePub()
    await _feed(runner, pub, "bob", 10)
    assert len(pub.sent) == 3


async def test_capped_peer_does_not_reach_the_driver():
    """The cap exists to stop burning tokens, so it has to short-circuit."""
    driver = _Counting()
    runner = DriverRunner(_cfg(), driver, max_turns=2)
    pub = _FakePub()
    await _feed(runner, pub, "bob", 10)
    assert driver.calls == 2


async def test_cap_is_per_peer():
    driver = _Counting()
    runner = DriverRunner(_cfg(), driver, max_turns=2)
    pub = _FakePub()
    await _feed(runner, pub, "bob", 5)
    await _feed(runner, pub, "carol", 1)
    assert [e.to for e in pub.sent] == ["bob", "bob", "carol"]


async def test_zero_means_no_cap():
    driver = _Counting()
    runner = DriverRunner(_cfg(), driver, max_turns=0)
    pub = _FakePub()
    await _feed(runner, pub, "bob", 25)
    assert len(pub.sent) == 25


async def _one(driver: Driver, env: Envelope) -> Envelope | None:
    runner = DriverRunner(_cfg(), driver)
    pub = _FakePub()
    await runner._handle_one(env, pub)  # type: ignore[arg-type]
    return pub.sent[0] if pub.sent else None


async def test_a_broadcast_is_answered_in_the_room():
    env = Envelope.new("user", "broadcast", "deploy", "ship it?")
    out = await _one(_Fixed("yes"), env)
    assert out is not None
    assert out.to == "broadcast"


async def test_a_direct_message_is_answered_privately():
    env = Envelope.new("bob", "alice", "question", "you around?")
    out = await _one(_Fixed("yep"), env)
    assert out is not None
    assert out.to == "bob"


async def test_the_topic_carries_forward_so_a_thread_stays_one_thread():
    env = Envelope.new("user", "broadcast", "deploy", "ship it?")
    out = await _one(_Fixed("yes"), env)
    assert out is not None
    assert out.topic == "deploy"


async def test_a_reply_can_pick_its_own_recipient():
    env = Envelope.new("user", "broadcast", "deploy", "ship it?")
    out = await _one(_Fixed(Reply("what do you think?", to="bob")), env)
    assert out is not None
    assert out.to == "bob"
    assert out.body == "what do you think?"


async def test_a_reply_can_pick_its_own_topic():
    env = Envelope.new("user", "broadcast", "deploy", "ship it?")
    out = await _one(_Fixed(Reply("unrelated", topic="lunch")), env)
    assert out is not None
    assert out.topic == "lunch"


async def test_an_agent_never_sends_to_itself():
    env = Envelope.new("user", "broadcast", "deploy", "ship it?")
    assert await _one(_Fixed(Reply("talking to myself", to="alice")), env) is None


async def test_a_blank_reply_is_not_sent():
    env = Envelope.new("bob", "alice", "t", "hi")
    assert await _one(_Fixed("   \n  "), env) is None


async def test_reply_to_points_at_the_message_being_answered():
    env = Envelope.new("bob", "alice", "t", "hi")
    out = await _one(_Fixed("hi back"), env)
    assert out is not None
    assert out.reply_to == env.msg_id


async def test_silent_driver_does_not_spend_a_turn():
    class _Silent(Driver):
        async def handle(self, env: Envelope) -> str | None:
            return None

    runner = DriverRunner(_cfg(), _Silent(), max_turns=2)
    pub = _FakePub()
    await _feed(runner, pub, "bob", 10)
    assert pub.sent == []
    assert runner._replies == {}

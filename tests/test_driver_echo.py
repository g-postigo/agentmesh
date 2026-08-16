from __future__ import annotations

from chatmesh import Envelope
from chatmesh.drivers import EchoDriver


async def test_answers_a_direct_message():
    reply = await EchoDriver(agent_name="alice").handle(
        Envelope.new("bob", "alice", "t", "you there?")
    )
    assert reply is not None
    assert "you there?" in reply.body


async def test_stays_quiet_on_a_broadcast_that_is_not_about_it():
    env = Envelope.new("user", "broadcast", "t", "anyone seen the logs?")
    assert await EchoDriver(agent_name="alice").handle(env) is None


async def test_speaks_up_when_the_broadcast_names_it():
    env = Envelope.new("user", "broadcast", "t", "Alice, can you check?")
    assert await EchoDriver(agent_name="alice").handle(env) is not None


async def test_does_not_answer_another_echo():
    """Two of these in a room used to ping-pong until the turn cap hit."""
    alice, bob = EchoDriver(agent_name="alice"), EchoDriver(agent_name="bob")
    first = await bob.handle(Envelope.new("user", "bob", "t", "hello"))
    assert first is not None
    assert await alice.handle(Envelope.new("bob", "alice", "t", first.body)) is None

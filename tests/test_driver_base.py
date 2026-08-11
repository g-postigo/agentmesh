from __future__ import annotations

import pytest

from chatmesh import Envelope
from chatmesh.drivers import Driver


class Echo(Driver):
    async def handle(self, env: Envelope) -> str | None:
        return f"echo: {env.body}"


class Silent(Driver):
    async def handle(self, env: Envelope) -> str | None:
        return None


async def test_echo_returns_string():
    d = Echo()
    await d.start()
    env = Envelope.new("alice", "bob", "greet", "hi")
    reply = await d.handle(env)
    await d.stop()
    assert reply == "echo: hi"


async def test_silent_returns_none():
    d = Silent()
    env = Envelope.new("alice", "bob", "greet", "hi")
    assert await d.handle(env) is None


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        Driver()  # type: ignore[abstract]

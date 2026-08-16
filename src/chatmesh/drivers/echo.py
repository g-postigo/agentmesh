from __future__ import annotations

from chatmesh.drivers.base import Driver, Reply
from chatmesh.envelope import BROADCAST, Envelope

MARKER = " here, you said: "


class EchoDriver(Driver):
    """An agent with no model behind it.

    Answers direct messages, and on the broadcast channel only speaks when
    its name comes up. Enough to see the mesh work end to end without a
    Claude or Kimi login, and the fastest way to tell whether a broken
    setup is the broker or the model.
    """

    def __init__(self, *, agent_name: str = "agent") -> None:
        self.agent_name = agent_name

    async def handle(self, env: Envelope) -> Reply | None:
        # Two of these pointed at each other would echo each other's echoes
        # until the turn cap cut them off, which as a first impression is a
        # hundred lines of noise.
        if MARKER in env.body:
            return None
        if env.to == BROADCAST and self.agent_name.lower() not in env.body.lower():
            return None
        return Reply(f"{self.agent_name}{MARKER}{env.body}")

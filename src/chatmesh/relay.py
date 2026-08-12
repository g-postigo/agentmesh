from __future__ import annotations

import asyncio
import logging

from nats.aio.msg import Msg

from chatmesh.config import Config
from chatmesh.envelope import BROADCAST, Envelope
from chatmesh.errors import EnvelopeError
from chatmesh.publisher import _connect

log = logging.getLogger("chatmesh.relay")

# Relays share this queue group, so running a second one for redundancy
# splits the traffic instead of duplicating every message.
QUEUE_GROUP = "chatmesh-relay"


class Relay:
    """Route agent.outbox.<from> traffic to per-recipient inbox subjects.

    - `env.to == "broadcast"` -> agent.broadcast.<topic>.<from>
    - otherwise               -> agent.inbox.<to>

    Publishing to an outbox is how agents send. Listeners subscribe to
    inbox and broadcast subjects. Something has to bridge the two, and
    this is it.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._nc = None

    async def run(self) -> None:
        self._nc = await _connect(self._config)
        try:
            await self._nc.subscribe("agent.outbox.>", queue=QUEUE_GROUP, cb=self._forward)
            await asyncio.Event().wait()
        finally:
            await self._nc.drain()

    async def _forward(self, msg: Msg) -> None:
        try:
            env = Envelope.from_json(msg.data)
        except EnvelopeError:
            return
        if env.to == BROADCAST:
            subject = f"agent.broadcast.{env.topic}.{env.from_}"
        else:
            subject = f"agent.inbox.{env.to}"
        assert self._nc is not None
        await self._nc.publish(subject, msg.data)

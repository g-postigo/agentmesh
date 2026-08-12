from __future__ import annotations

import asyncio
import contextlib
import logging

from nats.aio.msg import Msg

from chatmesh.config import Config
from chatmesh.durable import ensure_stream
from chatmesh.durable import subscribe as durable_subscribe
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
        self._js = None

    async def run(self) -> None:
        self._nc = await _connect(self._config)
        try:
            if self._config.durable:
                self._js = self._nc.jetstream()
                await ensure_stream(self._js)
                # The relay is the only thing moving outboxes to inboxes, so
                # anything sent while it is down has to wait for it, not
                # evaporate.
                await durable_subscribe(
                    self._js,
                    "agent.outbox.>",
                    durable=QUEUE_GROUP,
                    queue=QUEUE_GROUP,
                    cb=self._forward_durable,
                )
            else:
                await self._nc.subscribe("agent.outbox.>", queue=QUEUE_GROUP, cb=self._forward)
            await asyncio.Event().wait()
        finally:
            await self._nc.drain()

    async def _forward(self, msg: Msg) -> None:
        subject = self._route(msg)
        if subject is None:
            return
        assert self._nc is not None
        await self._nc.publish(subject, msg.data)

    async def _forward_durable(self, msg: Msg) -> None:
        subject = self._route(msg)
        if subject is None:
            with contextlib.suppress(Exception):
                await msg.term()
            return
        assert self._js is not None
        await self._js.publish(subject, msg.data)
        # Ack once the stream owns the forwarded copy.
        await msg.ack()

    def _route(self, msg: Msg) -> str | None:
        try:
            env = Envelope.from_json(msg.data)
        except EnvelopeError:
            return None
        if env.to == BROADCAST:
            return f"agent.broadcast.{env.topic}.{env.from_}"
        return f"agent.inbox.{env.to}"

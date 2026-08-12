from __future__ import annotations

import asyncio
import contextlib

from nats.aio.msg import Msg

from chatmesh.config import Config
from chatmesh.durable import consumer_name, ensure_stream
from chatmesh.durable import subscribe as durable_subscribe
from chatmesh.envelope import Envelope
from chatmesh.errors import EnvelopeError
from chatmesh.publisher import _connect
from chatmesh.sidecar import Sidecar


class Listener:
    def __init__(self, config: Config, sidecar: Sidecar) -> None:
        self._config = config
        self._sidecar = sidecar

    async def run(self) -> None:
        nc = await _connect(self._config)
        name = self._config.agent_name
        try:
            if self._config.durable:
                js = nc.jetstream()
                await ensure_stream(js)
                await durable_subscribe(
                    js,
                    f"agent.inbox.{name}",
                    durable=consumer_name("inbox", name),
                    cb=self._handle_durable,
                )
                await durable_subscribe(
                    js,
                    "agent.broadcast.>",
                    durable=consumer_name("broadcast", name),
                    cb=self._handle_durable,
                )
            else:
                await nc.subscribe(f"agent.inbox.{name}", cb=self._handle)
                await nc.subscribe("agent.broadcast.>", cb=self._handle)
            # Sleep until cancelled.
            await asyncio.Event().wait()
        finally:
            await nc.drain()

    async def _handle(self, msg: Msg) -> None:
        try:
            env = Envelope.from_json(msg.data)
        except EnvelopeError:
            return
        self._sidecar.append(env)

    async def _handle_durable(self, msg: Msg) -> None:
        try:
            env = Envelope.from_json(msg.data)
        except EnvelopeError:
            # Redelivering this forever would wedge the consumer, and no
            # amount of retrying is going to make it parse.
            with contextlib.suppress(Exception):
                await msg.term()
            return
        self._sidecar.append(env)
        # Ack only once it is on disk, so a crash before that replays it.
        await msg.ack()

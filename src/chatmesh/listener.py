from __future__ import annotations

import asyncio

from nats.aio.msg import Msg

from chatmesh.config import Config
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

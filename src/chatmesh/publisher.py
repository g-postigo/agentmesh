from __future__ import annotations

import nats

from chatmesh.config import Config
from chatmesh.durable import ensure_stream
from chatmesh.envelope import Envelope


class Publisher:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._nc: nats.NATS | None = None
        self._js = None

    async def connect(self) -> None:
        self._nc = await _connect(self._config)
        if self._config.durable:
            self._js = self._nc.jetstream()
            await ensure_stream(self._js)

    async def publish(self, env: Envelope) -> None:
        if self._nc is None:
            raise RuntimeError("call connect() before publish()")
        subject = f"agent.outbox.{env.from_}"
        if self._js is not None:
            # Waiting for the ack means the stream has it before we move on,
            # so a publisher that exits right away does not lose the message.
            await self._js.publish(subject, env.to_json())
            return
        await self._nc.publish(subject, env.to_json())
        await self._nc.flush()

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None


async def _connect(config: Config) -> nats.NATS:
    opts: dict = {"servers": [config.broker_url]}
    if config.nkey_seed_path is not None:
        opts["nkeys_seed"] = str(config.nkey_seed_path)
    return await nats.connect(**opts)

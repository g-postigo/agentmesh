from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from nats.aio.msg import Msg

from chatmesh.config import Config
from chatmesh.envelope import Envelope
from chatmesh.errors import EnvelopeError
from chatmesh.publisher import Publisher, _connect

log = logging.getLogger("chatmesh.driver")

EnvelopeFilter = Callable[[Envelope], bool]


class Driver(ABC):
    async def start(self) -> None:
        return None

    @abstractmethod
    async def handle(self, env: Envelope) -> str | None:
        """Return the reply body, or None to skip this message."""

    async def stop(self) -> None:
        return None


class DriverRunner:
    def __init__(
        self,
        config: Config,
        driver: Driver,
        *,
        accept: EnvelopeFilter | None = None,
    ) -> None:
        self._config = config
        self._driver = driver
        self._accept = accept or _default_accept
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()

    async def run(self) -> None:
        await self._driver.start()
        pub = Publisher(self._config)
        await pub.connect()
        nc = await _connect(self._config)
        try:
            name = self._config.agent_name
            await nc.subscribe(f"agent.inbox.{name}", cb=self._on_msg)
            await nc.subscribe("agent.broadcast.>", cb=self._on_msg)

            worker = asyncio.create_task(self._worker(pub))
            try:
                await asyncio.Event().wait()
            finally:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
        finally:
            await nc.drain()
            await pub.close()
            await self._driver.stop()

    async def _on_msg(self, msg: Msg) -> None:
        try:
            env = Envelope.from_json(msg.data)
        except EnvelopeError:
            return
        if env.from_ == self._config.agent_name:
            return  # own echo
        if not self._accept(env):
            return
        await self._queue.put(env)

    async def _worker(self, pub: Publisher) -> None:
        while True:
            env = await self._queue.get()
            try:
                reply = await self._driver.handle(env)
            except Exception as exc:  # noqa: BLE001
                log.warning("driver.handle raised: %s", exc)
                reply = None
            if reply is None:
                self._queue.task_done()
                continue
            out = Envelope.new(
                from_=self._config.agent_name,
                to=env.from_,
                topic="reply",
                body=reply,
                reply_to=env.msg_id,
                priority=env.priority,
            )
            try:
                await pub.publish(out)
            except Exception as exc:  # noqa: BLE001
                log.warning("publish failed: %s", exc)
            self._queue.task_done()


def _default_accept(env: Envelope) -> bool:
    # Accept everything that was not our own echo. Users can pass a stricter
    # filter (e.g. only direct-to-me, only certain topics) via `accept=`.
    return True

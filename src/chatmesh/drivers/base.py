from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from nats.aio.msg import Msg

from chatmesh.config import Config
from chatmesh.durable import consumer_name, ensure_stream
from chatmesh.durable import subscribe as durable_subscribe
from chatmesh.envelope import BROADCAST, Envelope
from chatmesh.errors import EnvelopeError
from chatmesh.publisher import Publisher, _connect

log = logging.getLogger("chatmesh.driver")

EnvelopeFilter = Callable[[Envelope], bool]

# Two drivers pointed at each other will talk until someone stops them, and
# every turn costs tokens. Cap how many replies we send to any one peer.
# Pass max_turns=0 to lift the cap.
DEFAULT_MAX_TURNS = 50

# How many recent message ids to remember when spotting a redelivery.
DEDUP_SIZE = 500


@dataclass(slots=True)
class Reply:
    """A reply that picks its own destination.

    `to=None` means answer where the message came from: the room if it was
    a broadcast, the sender if it was direct. `topic=None` keeps the topic
    of the message being answered, so a thread stays one thread.
    """

    body: str
    to: str | None = None
    topic: str | None = None


class Driver(ABC):
    async def start(self) -> None:
        return None

    @abstractmethod
    async def handle(self, env: Envelope) -> str | Reply | None:
        """Return the reply body, a Reply to choose where it goes, or None
        to stay quiet."""

    async def stop(self) -> None:
        return None


class DriverRunner:
    def __init__(
        self,
        config: Config,
        driver: Driver,
        *,
        accept: EnvelopeFilter | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self._config = config
        self._driver = driver
        self._accept = accept or _default_accept
        self._max_turns = max_turns
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()
        self._replies: dict[str, int] = {}
        self._silenced: set[str] = set()
        # Durable delivery is at-least-once, so the same message can arrive
        # twice. Answering it twice would be worse than the redelivery.
        self._seen_order: deque[str] = deque(maxlen=DEDUP_SIZE)
        self._seen: set[str] = set()

    async def run(self) -> None:
        await self._driver.start()
        pub = Publisher(self._config)
        await pub.connect()
        nc = await _connect(self._config)
        try:
            name = self._config.agent_name
            if self._config.durable:
                js = nc.jetstream()
                await ensure_stream(js)
                await durable_subscribe(
                    js,
                    f"agent.inbox.{name}",
                    durable=consumer_name("driver-inbox", name),
                    cb=self._on_durable_msg,
                )
                await durable_subscribe(
                    js,
                    "agent.broadcast.>",
                    durable=consumer_name("driver-broadcast", name),
                    cb=self._on_durable_msg,
                )
            else:
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
        env = self._read(msg)
        if env is not None:
            await self._queue.put(env)

    async def _on_durable_msg(self, msg: Msg) -> None:
        env = self._read(msg)
        # Ack whatever we are not going to answer, or the consumer redelivers
        # it forever. Ack what we take too: the reply is an LLM turn that can
        # run for minutes, and holding the ack open that long invites a
        # redelivery on top of the turn already in flight.
        with contextlib.suppress(Exception):
            await msg.ack()
        if env is not None:
            await self._queue.put(env)

    def _read(self, msg: Msg) -> Envelope | None:
        """Parse and filter, or None if this message is not ours to answer."""
        try:
            env = Envelope.from_json(msg.data)
        except EnvelopeError:
            return None
        if env.from_ == self._config.agent_name:
            return None  # own echo
        if env.msg_id in self._seen:
            return None  # redelivered
        self._remember(env.msg_id)
        if not self._accept(env):
            return None
        return env

    def _remember(self, msg_id: str) -> None:
        if len(self._seen_order) == self._seen_order.maxlen:
            self._seen.discard(self._seen_order[0])
        self._seen_order.append(msg_id)
        self._seen.add(msg_id)

    async def _worker(self, pub: Publisher) -> None:
        while True:
            env = await self._queue.get()
            try:
                await self._handle_one(env, pub)
            finally:
                self._queue.task_done()

    async def _handle_one(self, env: Envelope, pub: Publisher) -> None:
        # Check before calling the driver: no point spending an LLM turn on a
        # reply we are not going to send.
        if self._out_of_turns(env.from_):
            return
        try:
            reply = await self._driver.handle(env)
        except Exception as exc:  # noqa: BLE001
            log.warning("driver.handle raised: %s", exc)
            return
        if reply is None:
            return
        out = self._compose(env, reply)
        if out is None:
            return
        try:
            await pub.publish(out)
        except Exception as exc:  # noqa: BLE001
            log.warning("publish failed: %s", exc)
            return
        self._replies[env.from_] = self._replies.get(env.from_, 0) + 1

    def _compose(self, env: Envelope, reply: str | Reply) -> Envelope | None:
        if isinstance(reply, str):
            reply = Reply(reply)
        body = reply.body.strip()
        if not body:
            return None
        to = reply.to or (BROADCAST if env.to == BROADCAST else env.from_)
        if to == self._config.agent_name:
            log.warning("driver tried to reply to itself, dropping")
            return None
        return Envelope.new(
            from_=self._config.agent_name,
            to=to,
            topic=reply.topic or env.topic,
            body=body,
            reply_to=env.msg_id,
            priority=env.priority,
        )

    def _out_of_turns(self, peer: str) -> bool:
        if self._max_turns <= 0:
            return False
        if self._replies.get(peer, 0) < self._max_turns:
            return False
        if peer not in self._silenced:
            self._silenced.add(peer)
            log.warning(
                "hit the %d reply cap for %s, no longer replying to them. "
                "Raise it with max_turns=, or lift it with max_turns=0.",
                self._max_turns,
                peer,
            )
        return True


def _default_accept(env: Envelope) -> bool:
    # Accept everything that was not our own echo. Users can pass a stricter
    # filter (e.g. only direct-to-me, only certain topics) via `accept=`.
    return True

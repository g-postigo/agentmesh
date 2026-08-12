"""Durable delivery on top of JetStream.

Core NATS is at-most-once: a message sent while an agent is down is gone.
That is fine for a demo and wrong for a mesh where the watcher restarts
agents. Turn `durable = true` on in an agent's config and its messages go
through a JetStream stream instead, with a durable consumer per role, so
whatever arrived during the downtime is waiting when it comes back.

Publishing durably and consuming durably are separate choices. A durable
publisher still reaches plain core subscribers, so a mesh can be migrated
one process at a time.
"""

from __future__ import annotations

import contextlib
import re

from nats.js import JetStreamContext
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    RetentionPolicy,
    StreamConfig,
)
from nats.js.errors import BadRequestError, NotFoundError

STREAM = "CHATMESH"
SUBJECTS = ["agent.>"]

# A day of history and a bounded message count. Long enough to cover a
# restart or a night offline, short enough that the volume cannot run away.
MAX_AGE_SECONDS = 24 * 60 * 60
MAX_MSGS = 100_000

# An LLM turn can take minutes. Redelivering underneath one would mean two
# agents answering the same message, so give the ack plenty of room.
ACK_WAIT_SECONDS = 300

_INVALID = re.compile(r"[^A-Za-z0-9_-]")


async def ensure_stream(js: JetStreamContext) -> None:
    """Create the stream if it is not there. Safe to call from everywhere."""
    try:
        await js.stream_info(STREAM)
        return
    except NotFoundError:
        pass
    # Someone else may create it between our check and our add.
    with contextlib.suppress(BadRequestError):
        await js.add_stream(
            StreamConfig(
                name=STREAM,
                subjects=list(SUBJECTS),
                retention=RetentionPolicy.LIMITS,
                max_age=MAX_AGE_SECONDS,
                max_msgs=MAX_MSGS,
            )
        )


def consumer_name(role: str, agent: str) -> str:
    """A durable name JetStream will accept.

    Agent names are free-form, durable names are not: no dots, no wildcards,
    no spaces.
    """
    return f"{role}-{_INVALID.sub('-', agent)}"


async def subscribe(
    js: JetStreamContext,
    subject: str,
    *,
    durable: str,
    cb,
    queue: str | None = None,
):
    """Subscribe with a durable consumer and manual acks.

    The deliver policy only applies the first time this durable is created.
    An agent joining a mesh that has been running for a day starts from now
    rather than being handed a day of backlog, which for an LLM driver would
    be a large bill and a confusing first impression. Once the durable
    exists, it resumes from the last message it acked, which is the whole
    point of turning this on.
    """
    return await js.subscribe(
        subject,
        durable=durable,
        queue=queue,
        cb=cb,
        manual_ack=True,
        config=ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=ACK_WAIT_SECONDS,
            deliver_policy=DeliverPolicy.NEW,
        ),
    )

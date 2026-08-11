from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from chatmesh.errors import EnvelopeError

Priority = Literal["low", "normal", "high", "urgent"]
_PRIORITIES: frozenset[str] = frozenset(("low", "normal", "high", "urgent"))


@dataclass(slots=True)
class Envelope:
    msg_id: str
    from_: str
    to: str
    reply_to: str | None
    ts: str
    topic: str
    priority: Priority
    ttl_seconds: int
    body: str
    version: int = 1

    @classmethod
    def new(
        cls,
        from_: str,
        to: str,
        topic: str,
        body: str,
        *,
        priority: Priority = "normal",
        ttl_seconds: int = 3600,
        reply_to: str | None = None,
    ) -> Envelope:
        if priority not in _PRIORITIES:
            raise EnvelopeError(f"invalid priority: {priority!r}")
        if ttl_seconds < 0:
            raise EnvelopeError(f"ttl_seconds must be non-negative, got {ttl_seconds}")
        return cls(
            msg_id=str(uuid.uuid4()),
            from_=from_,
            to=to,
            reply_to=reply_to,
            ts=_now_iso(),
            topic=topic,
            priority=priority,
            ttl_seconds=ttl_seconds,
            body=body,
        )

    def to_json(self) -> bytes:
        data = asdict(self)
        # `from` is a Python keyword, so the dataclass field is `from_`.
        # On the wire we use the plain name.
        data["from"] = data.pop("from_")
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> Envelope:
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EnvelopeError(f"not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise EnvelopeError("envelope must be a JSON object")
        if "from" in parsed:
            parsed["from_"] = parsed.pop("from")
        try:
            env = cls(**parsed)
        except TypeError as exc:
            raise EnvelopeError(f"wrong fields: {exc}") from exc
        if env.priority not in _PRIORITIES:
            raise EnvelopeError(f"invalid priority: {env.priority!r}")
        if env.ttl_seconds < 0:
            raise EnvelopeError(f"ttl_seconds must be non-negative, got {env.ttl_seconds}")
        return env


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

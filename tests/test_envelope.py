from __future__ import annotations

import json

import pytest

from chatmesh import Envelope
from chatmesh.errors import EnvelopeError


def test_new_sets_id_and_timestamp():
    e = Envelope.new("alice", "bob", "greet", "hello")
    assert e.msg_id
    assert e.ts.endswith("Z")
    assert e.from_ == "alice"
    assert e.to == "bob"
    assert e.topic == "greet"
    assert e.body == "hello"
    assert e.priority == "normal"
    assert e.ttl_seconds == 3600
    assert e.reply_to is None
    assert e.version == 1


def test_round_trip():
    a = Envelope.new(
        "alice",
        "bob",
        "greet",
        "hello",
        priority="high",
        ttl_seconds=60,
        reply_to="abc-123",
    )
    b = Envelope.from_json(a.to_json())
    assert a == b


def test_wire_uses_from_not_from_underscore():
    e = Envelope.new("alice", "bob", "greet", "hello")
    d = json.loads(e.to_json())
    assert "from" in d
    assert "from_" not in d
    assert d["from"] == "alice"


def test_invalid_priority_on_new():
    with pytest.raises(EnvelopeError):
        Envelope.new("alice", "bob", "greet", "hi", priority="critical")  # type: ignore[arg-type]


def test_invalid_priority_on_decode():
    e = Envelope.new("alice", "bob", "greet", "hi")
    d = json.loads(e.to_json())
    d["priority"] = "critical"
    with pytest.raises(EnvelopeError):
        Envelope.from_json(json.dumps(d).encode("utf-8"))


def test_negative_ttl():
    with pytest.raises(EnvelopeError):
        Envelope.new("alice", "bob", "greet", "hi", ttl_seconds=-1)


def test_bad_shape():
    with pytest.raises(EnvelopeError):
        Envelope.from_json(b"not json")
    with pytest.raises(EnvelopeError):
        Envelope.from_json(b"[1, 2, 3]")
    with pytest.raises(EnvelopeError):
        Envelope.from_json(b'{"only_field": "here"}')

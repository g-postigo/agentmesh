from __future__ import annotations

import json
import urllib.error

import pytest

from chatmesh import Envelope
from chatmesh.drivers import OpenAIDriver


def _reply(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def _driver(monkeypatch, response, **kwargs) -> OpenAIDriver:
    """A driver whose HTTP call is replaced by a canned answer."""
    d = OpenAIDriver(agent_name="alice", peers=["bob", "user"], **kwargs)
    sent: list[list[dict]] = []

    def fake(messages):
        sent.append(messages)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(d, "_complete", fake)
    d.sent = sent  # type: ignore[attr-defined]
    return d


def _msg(body: str = "ship it?") -> Envelope:
    return Envelope.new("user", "broadcast", "deploy", body)


async def test_reply_comes_back_from_the_model(monkeypatch):
    d = _driver(monkeypatch, "looks good to me")
    reply = await d.handle(_msg())
    assert reply is not None
    assert reply.body == "looks good to me"


async def test_the_room_header_reaches_the_model(monkeypatch):
    d = _driver(monkeypatch, "ok")
    await d.handle(_msg())
    messages = d.sent[0]  # type: ignore[attr-defined]
    assert messages[0]["role"] == "system"
    assert "@skip" in messages[0]["content"]
    assert "[room: alice (you), bob, user]" in messages[-1]["content"]


async def test_routing_prefixes_work_like_the_other_drivers(monkeypatch):
    d = _driver(monkeypatch, "@bob: your call")
    reply = await d.handle(_msg())
    assert reply is not None
    assert reply.to == "bob"
    assert reply.body == "your call"


async def test_skip_stays_quiet(monkeypatch):
    assert await _driver(monkeypatch, "@skip").handle(_msg()) is None


async def test_history_is_carried_and_bounded(monkeypatch):
    d = _driver(monkeypatch, "ok", history=2)
    for i in range(5):
        await d.handle(_msg(f"message {i}"))
    # Two turns kept means four entries, and the system prompt is not one.
    assert len(d._turns) == 4
    last = d.sent[-1]  # type: ignore[attr-defined]
    assert last[0]["role"] == "system"
    assert len(last) == 6  # system + 4 history + the new user turn


async def test_a_server_error_goes_quiet_instead_of_crashing(monkeypatch):
    boom = urllib.error.URLError("connection refused")
    assert await _driver(monkeypatch, boom).handle(_msg()) is None


async def test_a_failed_call_is_not_written_into_history(monkeypatch):
    d = _driver(monkeypatch, RuntimeError("500"))
    await d.handle(_msg())
    assert d._turns == []


def test_base_url_trailing_slash_does_not_double_up():
    d = OpenAIDriver(agent_name="alice", base_url="http://localhost:11434/v1/")
    assert d.base_url == "http://localhost:11434/v1"


def test_request_shape(monkeypatch):
    """Pin the request body, since every compatible server keys off it."""
    d = OpenAIDriver(agent_name="alice", model="llama3", api_key="sk-test")
    captured = {}

    class _Resp:
        def read(self):
            return json.dumps(_reply("hi")).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["headers"] = dict(req.headers)
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert d._complete([{"role": "user", "content": "hi"}]) == "hi"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["body"]["model"] == "llama3"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_no_api_key_means_no_auth_header(monkeypatch):
    """Local servers like Ollama reject an empty bearer."""
    d = OpenAIDriver(agent_name="alice", api_key=None)
    captured = {}

    class _Resp:
        def read(self):
            return json.dumps(_reply("hi")).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: (captured.update(headers=dict(req.headers)), _Resp())[1],
    )
    d._complete([{"role": "user", "content": "hi"}])
    assert "Authorization" not in captured["headers"]


def test_an_empty_choices_list_is_an_error(monkeypatch):
    d = OpenAIDriver(agent_name="alice")

    class _Resp:
        def read(self):
            return b'{"choices": []}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp())
    with pytest.raises(RuntimeError, match="no choices"):
        d._complete([{"role": "user", "content": "hi"}])

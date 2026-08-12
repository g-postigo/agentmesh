"""Tests for the part of the drivers that reads a third party protocol.

Claude Code speaks stream-json, Kimi speaks JSON-RPC over stdin. Both are
other people's formats and both can change under us. These tests pin the
shapes we actually depend on, so a drift shows up here instead of as two
agents that quietly stopped talking.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from chatmesh.drivers import ClaudeDriver, KimiDriver


def _reader(*lines: str) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data((line + "\n").encode())
    reader.feed_eof()
    return reader


def _silent_reader() -> asyncio.StreamReader:
    """Never yields and never closes, so a read has to time out."""
    return asyncio.StreamReader()


def _assistant(*texts: str) -> str:
    blocks = [{"type": "text", "text": t} for t in texts]
    return json.dumps({"type": "assistant", "message": {"content": blocks}})


# --- Claude Code, stream-json ------------------------------------------------


async def test_claude_collects_text_until_the_result():
    d = ClaudeDriver(agent_name="alice")
    out = await d._read_until_result(
        _reader(
            json.dumps({"type": "system", "subtype": "init"}),
            _assistant("hello "),
            _assistant("world"),
            json.dumps({"type": "result", "subtype": "success"}),
        ),
        [],
    )
    assert "".join(out).strip() == "hello world"


async def test_claude_accepts_content_as_a_plain_string():
    d = ClaudeDriver(agent_name="alice")
    out = await d._read_until_result(
        _reader(
            json.dumps({"type": "assistant", "message": {"content": "flat"}}),
            json.dumps({"type": "result"}),
        ),
        [],
    )
    assert "".join(out) == "flat"


async def test_claude_ignores_non_text_blocks():
    """A tool_use block must not end up in the reply body."""
    d = ClaudeDriver(agent_name="alice")
    payload = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                    {"type": "text", "text": "done"},
                ]
            },
        }
    )
    out = await d._read_until_result(_reader(payload, json.dumps({"type": "result"})), [])
    assert "".join(out) == "done"


async def test_claude_skips_lines_that_are_not_json():
    d = ClaudeDriver(agent_name="alice")
    out = await d._read_until_result(
        _reader("not json at all", _assistant("still here"), json.dumps({"type": "result"})),
        [],
    )
    assert "".join(out) == "still here"


async def test_claude_raises_when_stdout_closes_before_the_result():
    d = ClaudeDriver(agent_name="alice")
    with pytest.raises(RuntimeError, match="closed stdout"):
        await d._read_until_result(_reader(_assistant("half a")), ["boom\n"])


async def test_claude_times_out_on_a_stalled_stream():
    d = ClaudeDriver(agent_name="alice", prompt_timeout=0.15)
    with pytest.raises(TimeoutError):
        await d._read_until_result(_silent_reader(), [])


# --- Kimi, JSON-RPC over the wire -------------------------------------------


class _FakeStdin:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return False

    def close(self) -> None:
        return None


class _FakeProc:
    def __init__(self, stdout: asyncio.StreamReader) -> None:
        self.stdin = _FakeStdin()
        self.stdout = stdout
        self.stderr = None
        self.pid = 4242


FIXED_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def fixed_request_id(monkeypatch: pytest.MonkeyPatch):
    """Pin the request id so a canned response can carry it."""
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(FIXED_ID))
    return FIXED_ID


def _content(text: str) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "event",
            "params": {"type": "ContentPart", "payload": {"type": "text", "text": text}},
        }
    )


def _result(req_id: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {}})


def _kimi(stdout: asyncio.StreamReader, **kwargs) -> KimiDriver:
    d = KimiDriver(agent_name="alice", allow_tools=True, **kwargs)
    d._proc = _FakeProc(stdout)  # type: ignore[assignment]
    return d


async def test_kimi_joins_content_parts_until_the_result(fixed_request_id):
    d = _kimi(_reader(_content("one "), _content("two"), _result(fixed_request_id)))
    assert await d._prompt("hi") == "one two"


async def test_kimi_returns_empty_on_a_wire_error(fixed_request_id):
    d = _kimi(
        _reader(json.dumps({"jsonrpc": "2.0", "id": fixed_request_id, "error": {"code": -1}}))
    )
    assert await d._prompt("hi") == ""


async def test_kimi_answers_a_permission_request_and_keeps_going(fixed_request_id):
    """The CLI can stop mid-turn to ask something. Nobody is watching, so the
    driver answers and the turn continues."""
    ask = json.dumps({"jsonrpc": "2.0", "id": "ask-1", "method": "request", "params": {}})
    d = _kimi(_reader(ask, _content("after the ask"), _result(fixed_request_id)))

    assert await d._prompt("hi") == "after the ask"

    sent = [json.loads(line) for line in d._proc.stdin.written]  # type: ignore[attr-defined]
    answer = next(m for m in sent if m.get("id") == "ask-1")
    assert answer["result"]["approved"] is True


async def test_kimi_raises_when_the_process_dies_mid_prompt(fixed_request_id):
    d = _kimi(_reader(_content("half a sentence")))
    with pytest.raises(RuntimeError, match="died mid-prompt"):
        await d._prompt("hi")


async def test_kimi_times_out_on_a_stalled_wire(fixed_request_id):
    d = _kimi(_silent_reader(), prompt_timeout=0.15)
    with pytest.raises(TimeoutError):
        await d._prompt("hi")


async def test_kimi_ignores_a_line_that_is_not_json(fixed_request_id):
    d = _kimi(_reader("garbage", _content("fine"), _result(fixed_request_id)))
    assert await d._prompt("hi") == "fine"


async def test_kimi_initialize_accepts_a_result(fixed_request_id):
    d = _kimi(
        _reader(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": fixed_request_id,
                    "result": {"server": {"protocol_version": "1.10"}},
                }
            )
        )
    )
    await d._initialize()
    sent = json.loads(d._proc.stdin.written[0])  # type: ignore[attr-defined]
    assert sent["method"] == "initialize"
    assert sent["params"]["client"]["name"] == "chatmesh"


async def test_kimi_initialize_raises_on_an_error(fixed_request_id):
    d = _kimi(
        _reader(json.dumps({"jsonrpc": "2.0", "id": fixed_request_id, "error": {"code": -1}}))
    )
    with pytest.raises(RuntimeError, match="initialize error"):
        await d._initialize()


async def test_kimi_initialize_raises_when_the_process_dies(fixed_request_id):
    d = _kimi(_reader())
    with pytest.raises(RuntimeError, match="died during initialize"):
        await d._initialize()


async def test_kimi_survives_a_protocol_version_it_does_not_know(fixed_request_id, caplog):
    """Drift should warn, not kill the driver."""
    d = _kimi(
        _reader(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": fixed_request_id,
                    "result": {"server": {"protocol_version": "9.99"}},
                }
            )
        )
    )
    await d._initialize()
    assert "drift" in caplog.text.lower()

from __future__ import annotations

from pathlib import Path

from chatmesh import Envelope
from chatmesh.sidecar import Sidecar, _tail_lines


def test_append_and_dedup(tmp_path: Path) -> None:
    s = Sidecar(tmp_path / "in.jsonl")
    e = Envelope.new("a", "b", "topic", "hi")
    assert s.append(e) is True
    assert s.append(e) is False
    assert s.has_seen(e.msg_id)


def test_read_new_from_offset(tmp_path: Path) -> None:
    s = Sidecar(tmp_path / "in.jsonl")
    a = Envelope.new("a", "b", "t", "1")
    b = Envelope.new("a", "b", "t", "2")
    s.append(a)
    offset = (tmp_path / "in.jsonl").stat().st_size
    s.append(b)
    envs = list(s.read_new(since_offset=offset))
    assert len(envs) == 1
    assert envs[0].msg_id == b.msg_id


def test_dedup_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "in.jsonl"
    s1 = Sidecar(path)
    e = Envelope.new("a", "b", "t", "hi")
    s1.append(e)

    s2 = Sidecar(path)
    assert s2.has_seen(e.msg_id)
    assert s2.append(e) is False


def test_restart_only_warms_the_tail(tmp_path: Path) -> None:
    """A long-lived sidecar must not be read end to end on restart."""
    path = tmp_path / "in.jsonl"
    s1 = Sidecar(path, dedup_size=5)
    envs = [Envelope.new("a", "b", "t", f"body {i}") for i in range(200)]
    for e in envs:
        s1.append(e)

    s2 = Sidecar(path, dedup_size=5)
    assert s2.has_seen(envs[-1].msg_id)
    assert s2.has_seen(envs[-5].msg_id)
    assert not s2.has_seen(envs[0].msg_id)


def test_tail_lines_reads_backwards_across_chunks(tmp_path: Path) -> None:
    path = tmp_path / "lines.txt"
    path.write_bytes(b"".join(f"line {i}\n".encode() for i in range(1000)))
    # Tiny chunk forces several backward reads and a partial first line.
    assert _tail_lines(path, 3, chunk=16) == [b"line 997", b"line 998", b"line 999"]


def test_tail_lines_handles_file_shorter_than_request(tmp_path: Path) -> None:
    path = tmp_path / "lines.txt"
    path.write_bytes(b"one\ntwo\n")
    assert _tail_lines(path, 10) == [b"one", b"two"]


def test_dedup_ring_evicts_oldest(tmp_path: Path) -> None:
    s = Sidecar(tmp_path / "in.jsonl", dedup_size=3)
    envs = [Envelope.new("a", "b", "t", str(i)) for i in range(5)]
    for e in envs:
        s.append(e)
    # First two evicted, last three remembered.
    assert not s.has_seen(envs[0].msg_id)
    assert not s.has_seen(envs[1].msg_id)
    assert s.has_seen(envs[2].msg_id)
    assert s.has_seen(envs[4].msg_id)

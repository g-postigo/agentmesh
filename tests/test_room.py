from __future__ import annotations

from chatmesh import Envelope
from chatmesh.drivers._chat import Room, default_room_prompt, parse_reply


def _to_room(sender: str = "user") -> Envelope:
    return Envelope.new(sender, "broadcast", "deploy", "ship it?")


def _direct(sender: str = "bob") -> Envelope:
    return Envelope.new(sender, "alice", "question", "you around?")


def test_header_marks_a_broadcast():
    room = Room("alice", ["bob", "user"])
    assert room.header(_to_room()) == (
        "[broadcast from=user topic=deploy]\n[room: alice (you), bob, user]"
    )


def test_header_marks_a_direct_message():
    room = Room("alice", ["bob", "user"])
    assert room.header(_direct()) == (
        "[direct from=bob topic=question]\n[room: alice (you), bob, user]"
    )


def test_roster_learns_names_from_traffic():
    room = Room("alice")
    assert room.peers == []
    room.header(_direct("carol"))
    assert room.peers == ["carol"]


def test_roster_never_lists_us_as_a_peer():
    room = Room("alice", ["alice", "bob"])
    room.header(_direct("alice"))
    assert room.peers == ["bob"]


def test_roster_does_not_repeat_a_name():
    room = Room("alice", ["bob"])
    room.header(_direct("bob"))
    room.header(_direct("bob"))
    assert room.peers == ["bob"]


def test_prompt_names_the_agent_and_the_others():
    prompt = default_room_prompt("alice", ["bob", "user"])
    assert "`alice`" in prompt
    assert "bob, user" in prompt
    assert "@skip" in prompt


def test_plain_text_answers_wherever_it_came_from():
    reply = parse_reply("sure, go ahead")
    assert reply is not None
    assert reply.to is None
    assert reply.body == "sure, go ahead"


def test_at_name_addresses_one_peer():
    reply = parse_reply("@bob: what do you think?")
    assert reply is not None
    assert reply.to == "bob"
    assert reply.body == "what do you think?"


def test_at_all_addresses_the_room():
    for prefix in ("@all", "@everyone", "@room", "@broadcast"):
        reply = parse_reply(f"{prefix}: heads up")
        assert reply is not None, prefix
        assert reply.to == "broadcast", prefix
        assert reply.body == "heads up", prefix


def test_name_is_case_insensitive():
    reply = parse_reply("@Bob: hi")
    assert reply is not None
    assert reply.to == "bob"


def test_skip_means_stay_quiet():
    for text in ("@skip", "@skip.", "  @skip  ", "@SKIP"):
        assert parse_reply(text) is None, text


def test_empty_reply_stays_quiet():
    assert parse_reply("") is None
    assert parse_reply("   \n  ") is None


def test_address_with_no_body_stays_quiet():
    assert parse_reply("@bob:") is None


def test_body_after_the_prefix_keeps_its_lines():
    reply = parse_reply("@bob: first\nsecond\nthird")
    assert reply is not None
    assert reply.to == "bob"
    assert reply.body == "first\nsecond\nthird"


def test_prefix_only_counts_on_the_first_line():
    """Otherwise any mention mid-message would silently reroute the reply."""
    reply = parse_reply("sounds good\n@bob: this is just text")
    assert reply is not None
    assert reply.to is None
    assert reply.body == "sounds good\n@bob: this is just text"


def test_at_sign_without_a_colon_is_just_text():
    reply = parse_reply("@bob what do you think?")
    assert reply is not None
    assert reply.to is None

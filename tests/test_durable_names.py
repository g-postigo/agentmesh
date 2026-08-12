from __future__ import annotations

from chatmesh.durable import MAX_AGE_SECONDS, STREAM, SUBJECTS, consumer_name


def test_consumer_name_strips_what_jetstream_rejects():
    # Durable names cannot carry dots, wildcards or spaces.
    assert consumer_name("inbox", "alice") == "inbox-alice"
    assert consumer_name("inbox", "team.alice") == "inbox-team-alice"
    assert consumer_name("inbox", "a b*c>d") == "inbox-a-b-c-d"


def test_stream_covers_every_agent_subject():
    assert SUBJECTS == ["agent.>"]
    assert STREAM == "CHATMESH"
    assert MAX_AGE_SECONDS == 24 * 60 * 60

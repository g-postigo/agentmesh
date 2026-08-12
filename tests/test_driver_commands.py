"""Structural tests for the driver command builders and prompt formatting.

No subprocess actually runs; these only verify the command list and prompt
shape. Full wire integration is manual because it needs the CLI installed.
"""

from __future__ import annotations

from chatmesh import Envelope
from chatmesh.drivers import ClaudeDriver, KimiDriver


def test_kimi_default_chat_mode_uses_agent_file():
    d = KimiDriver(agent_name="alice", session="alice")
    cmd = d.command()
    assert cmd[0] == "kimi"
    assert "--wire" in cmd
    assert "--session" in cmd
    assert cmd[cmd.index("--session") + 1] == "alice"
    # chat-only mode materializes an --agent-file with tools:[]
    assert "--agent-file" in cmd


def test_kimi_allow_tools_no_agent_file():
    d = KimiDriver(agent_name="alice", session="alice", allow_tools=True)
    cmd = d.command()
    assert "--agent-file" not in cmd


def test_kimi_custom_command():
    d = KimiDriver(
        agent_name="alice",
        binary="kimi.exe",
        session="alice",
        extra_args=["--foo"],
        allow_tools=True,
    )
    cmd = d.command()
    assert cmd[0] == "kimi.exe"
    assert "--session" in cmd
    assert cmd[cmd.index("--session") + 1] == "alice"
    assert "--foo" in cmd


def test_kimi_format_prompt_has_metadata():
    d = KimiDriver(agent_name="alice", allow_tools=True)
    env = Envelope.new("alice", "bob", "greet", "hi")
    p = d.format_prompt(env)
    assert "from=alice" in p
    assert "topic=greet" in p
    assert "hi" in p


def test_claude_first_turn_uses_session_id():
    d = ClaudeDriver(agent_name="alice", session_id="fixed-uuid", skip_permissions=False)
    cmd = d.command(first_turn=True)
    assert "--session-id" in cmd
    assert cmd[cmd.index("--session-id") + 1] == "fixed-uuid"
    assert "-r" not in cmd
    assert "--verbose" in cmd  # required by claude when using stream-json output


def test_claude_later_turn_resumes():
    d = ClaudeDriver(agent_name="alice", session_id="fixed-uuid", skip_permissions=False)
    cmd = d.command(first_turn=False)
    assert "-r" in cmd
    assert cmd[cmd.index("-r") + 1] == "fixed-uuid"
    assert "--session-id" not in cmd
    assert "--verbose" in cmd


def test_claude_chat_mode_disallows_tools():
    d = ClaudeDriver(agent_name="alice", session_id="x")
    cmd = d.command(first_turn=True)
    # --bare defaults off because it breaks Claude Code auth loading.
    assert "--bare" not in cmd
    assert "--append-system-prompt" in cmd
    assert "--disallowed-tools" in cmd
    # A representative tool must be blocked
    assert "Bash" in cmd
    assert "WebFetch" in cmd


def test_claude_allow_tools_omits_disallowed():
    d = ClaudeDriver(agent_name="alice", session_id="x", allow_tools=True)
    cmd = d.command(first_turn=True)
    assert "--disallowed-tools" not in cmd
    assert "--bare" not in cmd


def test_claude_bare_mode_opt_in():
    d = ClaudeDriver(agent_name="alice", session_id="x", bare_mode=True)
    assert "--bare" in d.command(first_turn=True)


def test_claude_custom_system_prompt():
    d = ClaudeDriver(agent_name="alice", session_id="x", system_prompt="be terse")
    cmd = d.command(first_turn=True)
    assert "--append-system-prompt" in cmd
    assert cmd[cmd.index("--append-system-prompt") + 1] == "be terse"


def test_claude_skip_permissions_flag():
    d = ClaudeDriver(agent_name="alice", session_id="x", skip_permissions=True)
    assert "--dangerously-skip-permissions" in d.command(first_turn=True)


def test_claude_model_flag():
    d = ClaudeDriver(
        agent_name="alice", session_id="x", model="claude-sonnet-5", skip_permissions=False
    )
    cmd = d.command(first_turn=True)
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5"


def test_claude_format_prompt_has_metadata():
    d = ClaudeDriver(agent_name="alice")
    env = Envelope.new("alice", "bob", "greet", "hi")
    p = d.format_prompt(env)
    assert "from=alice" in p
    assert "topic=greet" in p
    assert "hi" in p


def test_kimi_prompt_shows_the_room():
    d = KimiDriver(agent_name="alice", allow_tools=True, peers=["bob", "user"])
    env = Envelope.new("user", "broadcast", "deploy", "ship it?")
    p = d.format_prompt(env)
    assert "[broadcast from=user topic=deploy]" in p
    assert "[room: alice (you), bob, user]" in p


def test_claude_prompt_shows_the_room():
    d = ClaudeDriver(agent_name="alice", peers=["bob", "user"])
    env = Envelope.new("bob", "alice", "question", "you around?")
    p = d.format_prompt(env)
    assert "[direct from=bob topic=question]" in p
    assert "[room: alice (you), bob, user]" in p


def test_peers_reach_the_default_system_prompt():
    d = ClaudeDriver(agent_name="alice", peers=["bob", "user"])
    assert "bob, user" in d.system_prompt
    assert "@skip" in d.system_prompt

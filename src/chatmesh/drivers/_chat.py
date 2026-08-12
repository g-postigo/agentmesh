"""Shared helpers for putting a CLI driver into chat mode.

Both Kimi and Claude, out of the box, treat every message as a task and
have full tool access (filesystem, shell, MCP, plugins). That is not what
chatmesh users want when they wire two AI CLIs to chat with each other.

These helpers build a default system prompt and a Kimi agent spec that
constrain the driver to plain chat: no tools, no plugins, no reading the
filesystem, no inventing project context. They also carry the room: who
else is present, how a message arrived, and how a model says where its
answer should go.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from chatmesh.drivers.base import Reply
from chatmesh.envelope import BROADCAST, Envelope

# The full list of tool names Claude Code ships (as of v2.1.220). The
# names on the wire are stable; if Anthropic adds a tool, add it here.
CLAUDE_ALL_TOOLS = [
    "Task",
    "Bash",
    "CronCreate",
    "CronDelete",
    "CronList",
    "DesignSync",
    "Edit",
    "EnterWorktree",
    "ExitWorktree",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "ReportFindings",
    "ScheduleWakeup",
    "SendMessage",
    "Skill",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "ToolSearch",
    "WebFetch",
    "WebSearch",
    "Workflow",
    "Write",
]


class Room:
    """Who else is around, and how a message arrived.

    The roster starts from config and grows as names show up in traffic, so
    adding a third agent does not mean editing everyone else's config.
    """

    def __init__(self, me: str, peers: Iterable[str] = ()) -> None:
        self.me = me
        self._peers: list[str] = []
        for name in peers:
            self.note(name)

    def note(self, name: str) -> None:
        if name and name != self.me and name not in self._peers:
            self._peers.append(name)

    @property
    def peers(self) -> list[str]:
        return list(self._peers)

    def roster(self) -> str:
        return ", ".join([f"{self.me} (you)", *self._peers])

    def header(self, env: Envelope) -> str:
        self.note(env.from_)
        kind = "broadcast" if env.to == BROADCAST else "direct"
        return f"[{kind} from={env.from_} topic={env.topic}]\n[room: {self.roster()}]"


def default_room_prompt(agent_name: str, peers: Sequence[str] = ()) -> str:
    others = ", ".join(peers) if peers else "you will meet them as they speak"
    return (
        f"You are `{agent_name}`, one of several participants in a shared room.\n"
        f"Others here: {others}.\n"
        f"\n"
        f"Every message starts with two bracket lines. The first says whether it\n"
        f"went to the whole room or straight to you, who sent it, and the topic.\n"
        f"The second lists who is present.\n"
        f"\n"
        f"Saying where your answer goes:\n"
        f"- Start with `@name:` to answer that one participant privately.\n"
        f"- Start with `@all:` to answer the room.\n"
        f"- With no prefix your answer goes back where the message came from: the\n"
        f"  room for a broadcast, the sender for a direct message.\n"
        f"- Reply with exactly `@skip` to say nothing at all.\n"
        f"\n"
        f"Use `@skip` when the message is aimed at someone else and you have\n"
        f"nothing to add, when someone already answered it well, or when you\n"
        f"would only be agreeing or restating. A quiet room is fine.\n"
        f"\n"
        f"Speak when you were asked something, when the room was asked for\n"
        f"opinions and yours differs from what has been said, or when you know\n"
        f"something that changes the answer.\n"
        f"\n"
        f"You are talking, not working on a project. Do not read files, run\n"
        f"commands, or use tools of any kind. Do not invent context about the\n"
        f"sender, the environment, or a task list. If something would need tools,\n"
        f"say that you can only talk. Keep it to a couple of sentences unless\n"
        f"asked for more.\n"
    )


# `@name:` or `@all:` at the very start of a reply says where it goes.
_ADDRESS = re.compile(r"^@([A-Za-z0-9_.-]+)\s*:\s*", re.ASCII)
_SKIP = re.compile(r"^@skip\b[\s.!]*$", re.ASCII | re.IGNORECASE)
_ROOM_WORDS = frozenset({"all", "everyone", "room", "broadcast"})


def parse_reply(text: str) -> Reply | None:
    """Read a model's raw answer as a routed reply, or None to stay quiet."""
    text = text.strip()
    if not text:
        return None
    first, newline, rest = text.partition("\n")
    first = first.strip()
    if _SKIP.match(first):
        return None
    match = _ADDRESS.match(first)
    if match is None:
        return Reply(text)
    body = (first[match.end() :] + newline + rest).strip()
    if not body:
        return None
    name = match.group(1).lower()
    return Reply(body, to=BROADCAST if name in _ROOM_WORDS else name)


def materialize_kimi_chat_agent(agent_name: str, system_prompt: str) -> Path:
    """Write a temp Kimi agent spec + prompt for chat-only mode.

    Returns the path to the agent YAML. Caller is responsible for
    cleaning the parent tempdir when done (or leaving it; it is small).
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="chatmesh-kimi-"))
    prompt_path = tmpdir / "prompt.md"
    prompt_path.write_text(system_prompt, encoding="utf-8")
    yaml_path = tmpdir / "agent.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "agent:\n"
        f'  name: "{agent_name}"\n'
        '  designation: "chatmesh chat participant"\n'
        f"  system_prompt_path: {prompt_path.name}\n"
        "  tools: []\n"
        "  global_config:\n"
        "    yolo: true\n",
        encoding="utf-8",
    )
    return yaml_path

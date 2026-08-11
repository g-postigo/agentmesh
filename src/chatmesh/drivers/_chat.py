"""Shared helpers for putting a CLI driver into chat mode.

Both Kimi and Claude, out of the box, treat every message as a task and
have full tool access (filesystem, shell, MCP, plugins). That is not what
chatmesh users want when they wire two AI CLIs to chat with each other.

These helpers build a default system prompt and a Kimi agent spec that
constrain the driver to plain chat: no tools, no plugins, no reading the
filesystem, no inventing project context.
"""

import tempfile
from pathlib import Path

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


def default_chat_prompt(agent_name: str) -> str:
    return (
        f"You are `{agent_name}`, a participant in a text chat.\n"
        f"\n"
        f"Rules:\n"
        f"- Respond briefly and directly to what the other side sends.\n"
        f"- You are chatting, not working on a project. Do not read files, run\n"
        f"  commands, or use tools of any kind.\n"
        f"- Do not invent context about the sender, environment, or a task list.\n"
        f"- If a message asks for something that would require tools, reply that\n"
        f"  you can only chat.\n"
        f"- One or two short sentences per reply, unless asked for more.\n"
    )


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

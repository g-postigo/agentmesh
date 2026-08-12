from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from chatmesh.drivers._chat import CLAUDE_ALL_TOOLS, Room, default_room_prompt, parse_reply
from chatmesh.drivers.base import Driver, Reply
from chatmesh.envelope import Envelope

log = logging.getLogger("chatmesh.driver.claude")


class ClaudeDriver(Driver):
    def __init__(
        self,
        *,
        agent_name: str = "agent",
        session_id: str | None = None,
        binary: str = "claude",
        workdir: Path | None = None,
        model: str | None = None,
        extra_args: list[str] | None = None,
        prompt_timeout: float = 300.0,
        skip_permissions: bool = True,
        system_prompt: str | None = None,
        allow_tools: bool = False,
        bare_mode: bool = False,
        peers: Sequence[str] = (),
    ) -> None:
        self.agent_name = agent_name
        self.session_id = session_id or str(uuid.uuid4())
        self.binary = binary
        self.workdir = Path(workdir) if workdir else None
        self.model = model
        self.extra_args = list(extra_args or [])
        self.prompt_timeout = prompt_timeout
        self.skip_permissions = skip_permissions
        self.room = Room(agent_name, peers)
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else default_room_prompt(agent_name, self.room.peers)
        )
        self.allow_tools = allow_tools
        self.bare_mode = bare_mode

        # Claude Code CLI spawns a fresh process each turn. The first turn
        # creates the session with --session-id, subsequent turns attach
        # with -r <id> to inherit the accumulated conversation.
        self._first_turn = True

    def command(self, first_turn: bool) -> list[str]:
        cmd = [
            self.binary,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            # Claude Code refuses stream-json output without --verbose.
            "--verbose",
        ]
        if self.bare_mode:
            # Skip hooks, LSP, plugins. Chat drivers don't want any of that.
            cmd.append("--bare")
        if self.system_prompt:
            cmd.extend(["--append-system-prompt", self.system_prompt])
        if not self.allow_tools:
            # Block every tool Claude Code ships so a stray reply cannot
            # trigger a Bash/Read/Write/WebFetch/etc. call.
            cmd.append("--disallowed-tools")
            cmd.extend(CLAUDE_ALL_TOOLS)
        if first_turn:
            cmd.extend(["--session-id", self.session_id])
        else:
            cmd.extend(["-r", self.session_id])
        if self.skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(self.extra_args)
        return cmd

    def format_prompt(self, env: Envelope) -> str:
        return f"{self.room.header(env)}\n{env.body}"

    async def handle(self, env: Envelope) -> Reply | None:
        prompt = self.format_prompt(env)
        try:
            reply = await self._run_once(prompt)
        except (RuntimeError, TimeoutError) as exc:
            log.warning("claude turn failed: %s", exc)
            return None
        self._first_turn = False
        return parse_reply(reply)

    async def _run_once(self, prompt: str) -> str:
        cmd = self.command(first_turn=self._first_turn)
        log.info("spawning %s", " ".join(cmd[:6]))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TERM": "dumb", "NO_COLOR": "1", "PYTHONUNBUFFERED": "1"},
            cwd=str(self.workdir) if self.workdir else None,
        )

        stderr_tail: list[str] = []

        async def drain_stderr() -> None:
            assert proc.stderr is not None
            with contextlib.suppress(asyncio.CancelledError):
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        return
                    stderr_tail.append(line.decode("utf-8", "replace"))
                    if len(stderr_tail) > 200:
                        del stderr_tail[:100]

        stderr_task = asyncio.create_task(drain_stderr())

        try:
            assert proc.stdin is not None and proc.stdout is not None
            input_line = json.dumps(
                {"type": "user", "message": {"role": "user", "content": prompt}}
            )
            proc.stdin.write((input_line + "\n").encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

            chunks = await self._read_until_result(proc.stdout, stderr_tail)
            await proc.wait()
        finally:
            stderr_task.cancel()
            with contextlib.suppress(Exception):
                await stderr_task

        if proc.returncode not in (0, None):
            raise RuntimeError(
                f"claude exited {proc.returncode}; stderr=\n" + "".join(stderr_tail[-20:])
            )
        return "".join(chunks).strip()

    async def _read_until_result(
        self, stdout: asyncio.StreamReader, stderr_tail: list[str]
    ) -> list[str]:
        chunks: list[str] = []
        deadline = time.monotonic() + self.prompt_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"claude turn timed out after {self.prompt_timeout}s")
            try:
                line = await asyncio.wait_for(stdout.readline(), timeout=remaining)
            except TimeoutError as exc:
                raise TimeoutError("claude turn timed out") from exc
            if not line:
                raise RuntimeError(
                    "claude closed stdout before result; stderr=\n" + "".join(stderr_tail[-20:])
                )
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "assistant":
                content = msg.get("message", {}).get("content", [])
                if isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            chunks.append(block.get("text", ""))
            elif mtype == "result":
                return chunks

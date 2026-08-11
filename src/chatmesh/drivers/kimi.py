from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from chatmesh import __version__
from chatmesh.drivers._chat import default_chat_prompt, materialize_kimi_chat_agent
from chatmesh.drivers.base import Driver
from chatmesh.envelope import Envelope

log = logging.getLogger("chatmesh.driver.kimi")

PROTOCOL_VERSION = "1.10"


class KimiDriver(Driver):
    def __init__(
        self,
        *,
        agent_name: str = "agent",
        session: str = "chatmesh",
        binary: str = "kimi",
        workdir: Path | None = None,
        extra_args: list[str] | None = None,
        prompt_timeout: float = 300.0,
        system_prompt: str | None = None,
        agent_file: Path | None = None,
        allow_tools: bool = False,
    ) -> None:
        self.agent_name = agent_name
        self.session = session
        self.binary = binary
        self.workdir = Path(workdir) if workdir else None
        self.extra_args = list(extra_args or [])
        self.prompt_timeout = prompt_timeout
        self.system_prompt = (
            system_prompt if system_prompt is not None else default_chat_prompt(agent_name)
        )
        self.allow_tools = allow_tools

        if agent_file is not None:
            self.agent_file = Path(agent_file)
            self._agent_tmpdir: Path | None = None
        elif not allow_tools:
            # Materialize a chat-only agent spec (empty tools, chat prompt)
            # in a temp dir. We hold a reference so we can clean it up on stop.
            self.agent_file = materialize_kimi_chat_agent(agent_name, self.system_prompt)
            self._agent_tmpdir = self.agent_file.parent
        else:
            # allow_tools=True and no agent_file provided: fall back to
            # Kimi's built-in default agent, which has full tool access.
            self.agent_file = None
            self._agent_tmpdir = None

        self._proc: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_tail: list[str] = []

    def command(self) -> list[str]:
        cmd = [self.binary, "--wire", "--session", self.session]
        if self.workdir is not None:
            cmd.extend(["-w", str(self.workdir)])
        if self.agent_file is not None:
            cmd.extend(["--agent-file", str(self.agent_file)])
        cmd.extend(self.extra_args)
        return cmd

    def format_prompt(self, env: Envelope) -> str:
        return f"[msg from={env.from_} topic={env.topic}]\n{env.body}"

    async def start(self) -> None:
        await self._spawn()
        await self._initialize()

    async def stop(self) -> None:
        await self._close_proc()
        if self._agent_tmpdir is not None and self._agent_tmpdir.exists():
            with contextlib.suppress(Exception):
                shutil.rmtree(self._agent_tmpdir)

    async def handle(self, env: Envelope) -> str | None:
        text = self.format_prompt(env)
        try:
            reply = await self._prompt(text)
        except (RuntimeError, TimeoutError) as exc:
            log.warning("kimi prompt failed (%s), respawning", exc)
            await self._close_proc()
            await self._spawn()
            await self._initialize()
            try:
                reply = await self._prompt(text)
            except Exception as exc2:  # noqa: BLE001
                log.warning("kimi prompt failed after respawn: %s", exc2)
                return None
        return reply or None

    async def _spawn(self) -> None:
        if self.workdir is not None:
            self.workdir.mkdir(parents=True, exist_ok=True)
        cmd = self.command()
        log.info("spawning %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=32 * 1024 * 1024,
            env={**os.environ, "TERM": "dumb", "NO_COLOR": "1", "PYTHONUNBUFFERED": "1"},
        )
        self._stderr_tail = []
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        log.info("kimi pid=%s", self._proc.pid)

    async def _initialize(self) -> None:
        req_id = str(uuid.uuid4())
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "initialize",
                "params": {
                    "protocol_version": PROTOCOL_VERSION,
                    "client": {"name": "chatmesh", "version": __version__},
                    "capabilities": {"supports_question": False, "supports_plan_mode": False},
                },
            }
        )
        while True:
            msg = await self._read()
            if msg is None:
                raise RuntimeError(
                    "kimi died during initialize; stderr=\n" + "".join(self._stderr_tail)
                )
            if msg.get("id") == req_id and ("result" in msg or "error" in msg):
                if "error" in msg:
                    raise RuntimeError(f"initialize error: {msg['error']}")
                server = (msg.get("result") or {}).get("server", {})
                got = server.get("protocol_version", PROTOCOL_VERSION)
                if got and got != PROTOCOL_VERSION:
                    log.warning("wire protocol drift: expected=%s got=%s", PROTOCOL_VERSION, got)
                log.info("initialize ok, server=%s", server)
                return

    async def _prompt(self, text: str) -> str:
        req_id = str(uuid.uuid4())
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "prompt",
                "params": {"user_input": text},
            }
        )
        chunks: list[str] = []
        deadline = time.monotonic() + self.prompt_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"prompt {req_id} timed out after {self.prompt_timeout}s")
            try:
                msg = await asyncio.wait_for(self._read(), timeout=remaining)
            except TimeoutError as exc:
                raise TimeoutError(f"prompt {req_id} timed out") from exc
            if msg is None:
                raise RuntimeError("kimi died mid-prompt; stderr=\n" + "".join(self._stderr_tail))
            if msg.get("method") == "request":
                await self._auto_reply_request(msg)
                continue
            if msg.get("id") == req_id and ("result" in msg or "error" in msg):
                if "error" in msg:
                    log.warning("kimi wire error: %s", msg["error"])
                    return ""
                return "".join(chunks).strip()
            if msg.get("method") == "event":
                params = msg.get("params", {}) or {}
                if params.get("type") == "ContentPart":
                    payload = params.get("payload", {}) or {}
                    if payload.get("type") == "text":
                        chunks.append(payload.get("text", ""))

    async def _auto_reply_request(self, msg: dict) -> None:
        rid = msg.get("id")
        if rid is None:
            return
        await self._send(
            {"jsonrpc": "2.0", "id": rid, "result": {"approved": True, "allow": True, "answer": ""}}
        )

    async def _send(self, obj: dict) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _read(self) -> dict | None:
        assert self._proc is not None and self._proc.stdout is not None
        line = await self._proc.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"_raw": line.decode("utf-8", "replace")}

    async def _drain_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    return
                self._stderr_tail.append(line.decode("utf-8", "replace"))
                if len(self._stderr_tail) > 200:
                    self._stderr_tail = self._stderr_tail[-100:]

    async def _close_proc(self) -> None:
        if self._proc is None:
            return
        with contextlib.suppress(Exception):
            if self._proc.stdin is not None and not self._proc.stdin.is_closing():
                self._proc.stdin.close()
        try:
            self._proc.terminate()
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except Exception:  # noqa: BLE001
            with contextlib.suppress(Exception):
                self._proc.kill()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(Exception):
                await self._stderr_task
        self._proc = None
        self._stderr_task = None

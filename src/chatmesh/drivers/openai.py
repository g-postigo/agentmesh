from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Sequence

from chatmesh.drivers._chat import Room, default_room_prompt, parse_reply
from chatmesh.drivers.base import Driver, Reply
from chatmesh.envelope import Envelope

log = logging.getLogger("chatmesh.driver.openai")

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIDriver(Driver):
    """Any server that speaks the OpenAI chat completions API.

    That covers OpenAI, Ollama, LM Studio, llama.cpp, OpenRouter, Groq,
    vLLM and most things people self-host, so point `base_url` at yours.
    Unlike the Claude and Kimi drivers there is no CLI to install: this
    talks HTTP with the standard library.
    """

    def __init__(
        self,
        *,
        agent_name: str = "agent",
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        system_prompt: str | None = None,
        peers: Sequence[str] = (),
        timeout: float = 120.0,
        history: int = 20,
    ) -> None:
        self.agent_name = agent_name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.history = history
        self.room = Room(agent_name, peers)
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else default_room_prompt(agent_name, self.room.peers)
        )
        self._turns: list[dict] = []

    def format_prompt(self, env: Envelope) -> str:
        return f"{self.room.header(env)}\n{env.body}"

    async def handle(self, env: Envelope) -> Reply | None:
        prompt = self.format_prompt(env)
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self._turns,
            {"role": "user", "content": prompt},
        ]
        try:
            text = await asyncio.to_thread(self._complete, messages)
        except Exception as exc:  # noqa: BLE001
            # Going quiet beats crashing the agent over someone else's 500.
            log.warning("completion failed: %s", exc)
            return None

        self._turns.append({"role": "user", "content": prompt})
        self._turns.append({"role": "assistant", "content": text})
        if self.history:
            # Keep the tail. Chat context is not worth an unbounded list.
            del self._turns[: -self.history * 2]
        return parse_reply(text)

    def _complete(self, messages: list[dict]) -> str:
        body = json.dumps({"model": self.model, "messages": messages}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"{exc.code} from {self.base_url}: {detail}") from exc
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"no choices in response: {str(payload)[:200]}")
        return choices[0].get("message", {}).get("content") or ""

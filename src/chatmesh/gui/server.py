"""Web GUI for chatmesh.

Serves a small dark chat UI over HTTP + WebSocket. Subscribes to
`agent.inbox.<agent_name>`, `agent.outbox.>`, and `agent.broadcast.>`,
streams every envelope to connected browsers in real time, and exposes
a POST /send endpoint that publishes on behalf of the configured agent.

Optional dependency: install with `pip install chatmesh[gui]`.
"""

import asyncio
import contextlib
import json
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib import resources

from chatmesh.config import Config

HISTORY_LEN = 500
DEDUP_LEN = 1000


def _load_index_html() -> str:
    return resources.files("chatmesh.gui").joinpath("index.html").read_text(encoding="utf-8")


def build_app(config: Config, auth_token: str = ""):
    """Construct the FastAPI app. Imports fastapi lazily so chatmesh
    itself doesn't require the gui extras when the GUI is unused."""
    try:
        from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse, Response
        from pydantic import BaseModel
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "GUI dependencies missing. Install with: pip install chatmesh[gui]"
        ) from exc

    import nats

    index_html = _load_index_html().replace("__AGENT_NAME__", config.agent_name)

    state = {
        "history": deque(maxlen=HISTORY_LEN),
        "seen": deque(maxlen=DEDUP_LEN),
        "sockets": set(),
        "nc": None,
    }

    async def broadcast(entry: dict) -> None:
        dead = []
        for ws in state["sockets"]:
            try:
                await ws.send_json(entry)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            state["sockets"].discard(ws)

    async def on_nats_msg(msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
        except Exception:  # noqa: BLE001
            return
        if not isinstance(payload, dict):
            return
        if payload.get("from") == config.agent_name:
            return  # skip own echoes
        mid = payload.get("msg_id")
        if mid and mid in state["seen"]:
            return
        if mid:
            state["seen"].append(mid)
        entry = {
            "rx_ts": datetime.now(UTC).isoformat(),
            "subject": msg.subject,
            "from": payload.get("from", "?"),
            "to": payload.get("to", "?"),
            "topic": payload.get("topic", "?"),
            "priority": payload.get("priority", "normal"),
            "body": payload.get("body", ""),
            "msg_id": mid or "",
            "reply_to": payload.get("reply_to"),
        }
        state["history"].append(entry)
        await broadcast(entry)

    async def nats_worker() -> None:
        while True:
            try:
                state["nc"] = await nats.connect(
                    config.broker_url,
                    allow_reconnect=True,
                    max_reconnect_attempts=-1,
                    reconnect_time_wait=2,
                )
                await state["nc"].subscribe(f"agent.inbox.{config.agent_name}", cb=on_nats_msg)
                await state["nc"].subscribe("agent.outbox.>", cb=on_nats_msg)
                await state["nc"].subscribe("agent.broadcast.>", cb=on_nats_msg)
                while state["nc"].is_connected:
                    await asyncio.sleep(30)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(nats_worker())
        yield
        task.cancel()
        with contextlib.suppress(Exception):
            await task

    app = FastAPI(lifespan=lifespan)

    def _check_bearer(value: str | None) -> bool:
        if not auth_token:
            return True
        if not value:
            return False
        return value.strip() == f"Bearer {auth_token}"

    class SendPayload(BaseModel):
        to: str
        body: str
        priority: str = "normal"
        topic: str = "gui"
        reply_to: str | None = None

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        resp = HTMLResponse(index_html)
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'none'"
        )
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.get("/history")
    async def history() -> list[dict]:
        return list(state["history"])

    @app.post("/send")
    async def send(msg: SendPayload, authorization: str | None = Header(default=None)) -> dict:
        if not _check_bearer(authorization):
            raise HTTPException(status_code=401, detail="unauthorized")
        nc = state["nc"]
        if nc is None or not nc.is_connected:
            return {"ok": False, "error": "broker not connected"}
        env = {
            "msg_id": str(uuid.uuid4()),
            "from": config.agent_name,
            "to": msg.to,
            "reply_to": msg.reply_to,
            "ts": datetime.now(UTC).isoformat(),
            "topic": msg.topic,
            "priority": msg.priority,
            "ttl_seconds": 3600,
            "body": msg.body,
            "version": 1,
        }
        subject = f"agent.outbox.{config.agent_name}"
        await nc.publish(subject, json.dumps(env).encode())
        # Echo to sockets so the sender sees their own message immediately.
        # Use the subject the relay will forward it to, so channel filters
        # in the UI (broadcast, DM) match. If no relay is running, this
        # subject is still the meaningful destination for display.
        if msg.to == "broadcast":
            echo_subject = f"agent.broadcast.{msg.topic}.{config.agent_name}"
        else:
            echo_subject = f"agent.inbox.{msg.to}"
        echo = {**env, "rx_ts": env["ts"], "subject": echo_subject}
        state["history"].append(echo)
        await broadcast(echo)
        return {"ok": True, "msg_id": env["msg_id"], "subject": subject}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, token: str | None = Query(default=None)) -> None:
        if auth_token and token != auth_token:
            await ws.close(code=4401)
            return
        await ws.accept()
        state["sockets"].add(ws)
        try:
            for entry in list(state["history"]):
                await ws.send_json(entry)
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            state["sockets"].discard(ws)

    _MANIFEST = {
        "name": "chatmesh",
        "short_name": "chatmesh",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0b0e14",
        "theme_color": "#7aa2f7",
    }

    @app.get("/manifest.webmanifest")
    async def manifest() -> JSONResponse:
        return JSONResponse(_MANIFEST, media_type="application/manifest+json")

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    return app


def run(config: Config, host: str = "127.0.0.1", port: int = 8765, auth_token: str = "") -> None:
    try:
        import uvicorn
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "GUI dependencies missing. Install with: pip install chatmesh[gui]"
        ) from exc
    app = build_app(config, auth_token=auth_token)
    uvicorn.run(app, host=host, port=port, log_level="warning")

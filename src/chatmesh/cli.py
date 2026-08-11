from __future__ import annotations

import argparse
import asyncio
import contextlib
import subprocess
import sys
import uuid
from pathlib import Path

from chatmesh.config import Config
from chatmesh.drivers import ClaudeDriver, DriverRunner, KimiDriver
from chatmesh.envelope import Envelope, Priority
from chatmesh.listener import Listener
from chatmesh.publisher import Publisher
from chatmesh.relay import Relay
from chatmesh.sidecar import Sidecar
from chatmesh.watcher import Watcher

# Stable namespace for turning agent names into Claude session UUIDs.
_CLAUDE_SESSION_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="chatmesh")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_listen = sub.add_parser("listen", help="subscribe and write messages to a sidecar")
    p_listen.add_argument("--config", type=Path, required=True)

    p_pub = sub.add_parser("publish", help="publish one message")
    p_pub.add_argument("--config", type=Path, required=True)
    p_pub.add_argument("--to", required=True)
    p_pub.add_argument("--topic", required=True)
    p_pub.add_argument("--priority", default="normal", choices=("low", "normal", "high", "urgent"))
    p_pub.add_argument("--ttl", type=int, default=3600)
    p_pub.add_argument("--reply-to", default=None)
    p_pub.add_argument("body")

    p_watch = sub.add_parser("watch", help="respawn a command forever")
    p_watch.add_argument("--config", type=Path, required=True)
    p_watch.add_argument("command", nargs=argparse.REMAINDER)

    p_drive = sub.add_parser("drive", help="run an AI driver against this agent's inbox")
    p_drive.add_argument("--config", type=Path, required=True)
    p_drive.add_argument("--driver", required=True, choices=("kimi", "claude"))
    p_drive.add_argument("--session", default=None, help="session name (default: agent_name)")
    p_drive.add_argument("--binary", default=None, help="path to the CLI binary")
    p_drive.add_argument("--workdir", type=Path, default=None)
    p_drive.add_argument("--model", default=None, help="model name (claude only)")
    p_drive.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="path to a markdown/text file with a custom system prompt for the driver",
    )
    p_drive.add_argument(
        "--agent-file",
        type=Path,
        default=None,
        help="kimi only: path to a custom Kimi agent YAML (overrides the built-in chat spec)",
    )
    p_drive.add_argument(
        "--allow-tools",
        action="store_true",
        help=(
            "allow the driver to use tools (filesystem, shell, MCP). "
            "Off by default; drivers run chat-only."
        ),
    )

    p_relay = sub.add_parser(
        "relay", help="forward agent.outbox.<from> to inbox and broadcast subjects"
    )
    p_relay.add_argument("--config", type=Path, required=True)

    sub.add_parser("bootstrap", help="create demo configs and start the local broker")

    p_gui = sub.add_parser("gui", help="run the web UI")
    p_gui.add_argument("--config", type=Path, required=True)
    p_gui.add_argument("--host", default="127.0.0.1")
    p_gui.add_argument("--port", type=int, default=8765)
    p_gui.add_argument("--auth-token", default="", help="bearer token to gate /send and /ws")

    args = parser.parse_args(argv)
    if args.cmd == "bootstrap":
        return _cmd_bootstrap()

    cfg = Config.load(args.config)

    if args.cmd == "listen":
        return _cmd_listen(cfg)
    if args.cmd == "publish":
        return _cmd_publish(cfg, args)
    if args.cmd == "watch":
        return _cmd_watch(cfg, args)
    if args.cmd == "drive":
        return _cmd_drive(cfg, args)
    if args.cmd == "relay":
        return _cmd_relay(cfg)
    if args.cmd == "gui":
        return _cmd_gui(cfg, args)
    return 2


def _cmd_listen(cfg: Config) -> int:
    sidecar = Sidecar(cfg.sidecar_path)
    listener = Listener(cfg, sidecar)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(listener.run())
    return 0


def _cmd_publish(cfg: Config, args: argparse.Namespace) -> int:
    env = Envelope.new(
        from_=cfg.agent_name,
        to=args.to,
        topic=args.topic,
        body=args.body,
        priority=_as_priority(args.priority),
        ttl_seconds=args.ttl,
        reply_to=args.reply_to,
    )

    async def _go() -> None:
        pub = Publisher(cfg)
        await pub.connect()
        await pub.publish(env)
        await pub.close()

    asyncio.run(_go())
    sys.stdout.write(env.msg_id + "\n")
    return 0


def _cmd_watch(cfg: Config, args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        sys.stderr.write("watch: no command given\n")
        return 2
    w = Watcher(command, cfg.log_path)
    w.run()
    return 0  # never reached; run() calls sys.exit


def _cmd_relay(cfg: Config) -> int:
    relay = Relay(cfg)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(relay.run())
    return 0


def _cmd_drive(cfg: Config, args: argparse.Namespace) -> int:
    session = args.session or cfg.agent_name
    system_prompt = None
    if args.system_prompt_file is not None:
        system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    if args.driver == "kimi":
        driver = KimiDriver(
            agent_name=cfg.agent_name,
            session=session,
            binary=args.binary or "kimi",
            workdir=args.workdir,
            system_prompt=system_prompt,
            agent_file=args.agent_file,
            allow_tools=args.allow_tools,
        )
    else:  # claude
        # Claude requires a UUID for --session-id. Derive one deterministically
        # from the session name so restarts keep the same conversation.
        session_id = str(uuid.uuid5(_CLAUDE_SESSION_NAMESPACE, session))
        driver = ClaudeDriver(
            agent_name=cfg.agent_name,
            session_id=session_id,
            binary=args.binary or "claude",
            workdir=args.workdir,
            model=args.model,
            system_prompt=system_prompt,
            allow_tools=args.allow_tools,
        )
    runner = DriverRunner(cfg, driver)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(runner.run())
    return 0


def _cmd_gui(cfg: Config, args: argparse.Namespace) -> int:
    try:
        from chatmesh.gui import run as run_gui
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"error: {exc}\n")
        return 1
    with contextlib.suppress(KeyboardInterrupt):
        run_gui(cfg, host=args.host, port=args.port, auth_token=args.auth_token)
    return 0


def _cmd_bootstrap() -> int:
    root = _find_repo_root(Path.cwd())
    if root is None:
        sys.stderr.write(
            "error: bootstrap must run inside a cloned chatmesh repo "
            "(no pyproject.toml + broker/docker-compose.yml found walking up from cwd)\n"
        )
        return 1
    broker_yml = root / "broker" / "docker-compose.yml"

    mesh = Path.cwd() / "mesh"
    mesh.mkdir(exist_ok=True)
    # alice and bob are AI agents. user is you, the human, for the GUI and
    # for sending kickoff messages from the command line.
    for name in ("alice", "bob", "user"):
        cfg_path = mesh / f"{name}.toml"
        if cfg_path.exists():
            print(f"kept existing {cfg_path}")
        else:
            cfg_path.write_text(_config_template(name), encoding="utf-8")
            print(f"wrote {cfg_path}")

    print("starting broker...")
    rc = subprocess.run(
        ["docker", "compose", "-f", str(broker_yml), "up", "-d"],
        check=False,
    ).returncode
    if rc != 0:
        sys.stderr.write("error: docker compose failed (is Docker running?)\n")
        return rc

    print()
    print("broker is up on nats://127.0.0.1:4222")
    print()
    print("next, in separate terminals:")
    print()
    print("  1. relay:")
    print("       chatmesh relay --config mesh/user.toml")
    print()
    print("  2. GUI (open http://127.0.0.1:8765 in a browser after it starts):")
    print("       chatmesh gui --config mesh/user.toml")
    print()
    print("  3. one or both AI drivers (pick kimi or claude, whichever CLI you have):")
    print("       chatmesh drive --config mesh/alice.toml --driver claude")
    print("       chatmesh drive --config mesh/bob.toml   --driver kimi")
    print()
    print("  4. send a message from you to bob:")
    print(
        "       chatmesh publish --config mesh/user.toml --to bob --topic hello "
        '"reply with just: ok"'
    )
    print()
    print("stop the broker when done:")
    print(f"  docker compose -f {broker_yml.relative_to(root)} down")
    return 0


def _find_repo_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists() and (p / "broker" / "docker-compose.yml").exists():
            return p
    return None


def _config_template(name: str) -> str:
    return (
        f'broker_url = "nats://127.0.0.1:4222"\n'
        f'agent_name = "{name}"\n'
        f'sidecar_path = "{name}.jsonl"\n'
        f'log_path = "{name}.log"\n'
    )


def _as_priority(value: str) -> Priority:
    # argparse already restricts choices; the cast is for the type checker.
    return value  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())

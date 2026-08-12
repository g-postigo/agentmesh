from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from chatmesh.errors import ChatmeshError


class ConfigError(ChatmeshError):
    pass


@dataclass(slots=True)
class Config:
    broker_url: str
    agent_name: str
    sidecar_path: Path
    log_path: Path
    ca_pin_path: Path | None = None
    nkey_seed_path: Path | None = None
    peers: list[str] = field(default_factory=list)
    durable: bool = False

    @classmethod
    def load(cls, path: Path) -> Config:
        path = Path(path)
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except OSError as exc:
            raise ConfigError(f"cannot open config: {exc}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"bad TOML in {path}: {exc}") from exc

        base = path.parent

        def get(key: str, required: bool = True) -> str | None:
            value = data.get(key)
            if value is None:
                if required:
                    raise ConfigError(f"missing key: {key}")
                return None
            if not isinstance(value, str):
                raise ConfigError(f"{key} must be a string")
            return value

        def get_names(key: str) -> list[str]:
            value = data.get(key)
            if value is None:
                return []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{key} must be a list of strings")
            return list(value)

        def get_flag(key: str) -> bool:
            value = data.get(key)
            if value is None:
                return False
            if not isinstance(value, bool):
                raise ConfigError(f"{key} must be true or false")
            return value

        def resolve(value: str | None) -> Path | None:
            if value is None:
                return None
            p = Path(value)
            return p if p.is_absolute() else (base / p).resolve()

        return cls(
            broker_url=get("broker_url"),  # type: ignore[arg-type]
            agent_name=get("agent_name"),  # type: ignore[arg-type]
            sidecar_path=resolve(get("sidecar_path")),  # type: ignore[arg-type]
            log_path=resolve(get("log_path")),  # type: ignore[arg-type]
            ca_pin_path=resolve(get("ca_pin_path", required=False)),
            nkey_seed_path=resolve(get("nkey_seed_path", required=False)),
            peers=get_names("peers"),
            durable=get_flag("durable"),
        )

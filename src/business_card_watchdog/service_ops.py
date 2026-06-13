from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig, config_home


SERVICE_NAME = "business-card-watchdog.service"


@dataclass(frozen=True)
class UserServiceStatus:
    unit_path: str
    installed: bool
    service_name: str = SERVICE_NAME
    start_command: str = f"systemctl --user start {SERVICE_NAME}"
    enable_command: str = f"systemctl --user enable {SERVICE_NAME}"
    daemon_reload_command: str = "systemctl --user daemon-reload"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def user_systemd_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"


def service_unit_path() -> Path:
    return user_systemd_dir() / SERVICE_NAME


def render_user_service(config: AppConfig) -> str:
    command = f"{sys.executable} -m business_card_watchdog.cli --config {config.config_path} watch"
    return f"""[Unit]
Description=Business Card Watchdog watched-folder service
After=default.target

[Service]
Type=simple
ExecStart={command}
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def install_user_service(config: AppConfig) -> UserServiceStatus:
    config_home().mkdir(parents=True, exist_ok=True)
    path = service_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_user_service(config), encoding="utf-8")
    return service_status()


def uninstall_user_service() -> UserServiceStatus:
    path = service_unit_path()
    if path.exists():
        path.unlink()
    return service_status()


def service_status() -> UserServiceStatus:
    path = service_unit_path()
    return UserServiceStatus(unit_path=str(path), installed=path.exists())


"""El launcher de WhatsApp usa sys.executable -m uvicorn y logs persistentes."""
from __future__ import annotations

import sys

from core.services.microservice_launcher import MicroserviceLauncher


def test_launch_command_uses_current_python():
    launcher = MicroserviceLauncher()
    cmd = launcher.launch_command()
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "uvicorn", "main:app"]
    assert "--port" in cmd and "8000" in cmd


def test_log_file_is_persistent_not_devnull():
    launcher = MicroserviceLauncher()
    log_path = launcher.log_file_path()
    assert log_path.as_posix().endswith("logs/whatsapp_service.log")

    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "core" / "services" / "microservice_launcher.py"
    text = src.read_text(encoding="utf-8")
    assert "stdout=subprocess.DEVNULL" not in text, "los logs no deben ocultarse"


def test_startup_wait_is_at_least_30_seconds():
    assert MicroserviceLauncher.STARTUP_TIMEOUT_SECONDS >= 30

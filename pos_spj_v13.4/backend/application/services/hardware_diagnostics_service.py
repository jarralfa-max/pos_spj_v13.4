"""Hardware diagnostics service — keeps serial/socket/subprocess out of PyQt (FASE 8)."""

from __future__ import annotations

import platform

from backend.application.dto.diagnostics import DiagnosticResult


class HardwareDiagnosticsService:
    """Probes scale / drawer / network; the UI only issues commands and renders results."""

    def test_scale(self, port: str, baud: int) -> DiagnosticResult:
        try:
            import serial

            with serial.Serial(port, int(baud), timeout=2) as connection:
                data = connection.read(10)
            return DiagnosticResult.success(f"Puerto {port} OK — {len(data)} bytes recibidos")
        except ImportError:
            return DiagnosticResult.failure("pyserial no instalado — pip install pyserial")
        except Exception as exc:
            return DiagnosticResult.failure(str(exc))

    def open_drawer(self, *, method: str, command_hex: str, location: str, fallback_port: str) -> DiagnosticResult:
        try:
            command_bytes = bytes(int(part, 16) for part in (command_hex or "").split())
        except ValueError:
            return DiagnosticResult.failure("Formato de comando inválido. Ejemplo: 1B 70 00 19 FA")
        try:
            via_printer = "impresora" in (method or "").lower()
            if via_printer and ":" in (location or ""):
                import socket

                ip, port = location.split(":", 1)
                with socket.socket() as sock:
                    sock.settimeout(3)
                    sock.connect((ip, int(port)))
                    sock.sendall(command_bytes)
            else:
                import serial

                port = location if via_printer else fallback_port
                with serial.Serial(port, 9600, timeout=2) as connection:
                    connection.write(command_bytes)
            return DiagnosticResult.success("Comando enviado")
        except Exception as exc:
            return DiagnosticResult.failure(str(exc))

    def ping_gateway(self, gateway: str) -> DiagnosticResult:
        gateway = (gateway or "").strip()
        if not gateway:
            return DiagnosticResult.failure("Ingresa el gateway primero.")
        try:
            import subprocess

            param = "-n" if platform.system().lower() == "windows" else "-c"
            result = subprocess.run(
                ["ping", param, "1", gateway],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return DiagnosticResult.success(f"{gateway} responde")
            return DiagnosticResult.failure(f"{gateway} sin respuesta")
        except Exception as exc:
            return DiagnosticResult.failure(str(exc))

    def current_ip(self) -> DiagnosticResult:
        try:
            import socket

            hostname = socket.gethostname()
            return DiagnosticResult.success(f"IP actual: {socket.gethostbyname(hostname)}  ({hostname})")
        except Exception as exc:
            return DiagnosticResult.failure(str(exc))

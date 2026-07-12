# core/services/microservice_launcher.py
"""Auto-arranque del microservicio WhatsApp si no está corriendo."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger("spj.services.launcher")


class MicroserviceLauncher:
    """Inicia automáticamente el microservicio WhatsApp si está disponible."""

    _instance: MicroserviceLauncher | None = None
    _lock = threading.Lock()

    STARTUP_TIMEOUT_SECONDS = 30

    def __init__(self, app_root: Path | None = None) -> None:
        self.app_root = app_root or Path(__file__).parent.parent.parent.parent
        self.microservice_root = self.app_root / "whatsapp_service"
        self.process: subprocess.Popen | None = None
        self.running = False

    @classmethod
    def get_instance(cls, app_root: Path | None = None) -> MicroserviceLauncher:
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(app_root)
        return cls._instance

    def launch_command(self) -> list[str]:
        """Comando canónico: mismo intérprete del POS, sin depender del PATH."""
        return [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", "8000",
        ]

    def log_file_path(self) -> Path:
        """Log persistente del microservicio (logs/whatsapp_service.log)."""
        return self.app_root / "logs" / "whatsapp_service.log"

    def is_healthy(self, timeout: float = 2.0) -> bool:
        """Verifica si el microservicio está respondiendo."""
        try:
            resp = urllib.request.urlopen("http://localhost:8000/health", timeout=timeout)
            return resp.status == 200
        except (urllib.error.URLError, Exception):
            return False

    def try_start(self) -> bool:
        """Intenta arrancar el microservicio. Retorna True si está disponible."""
        if self.is_healthy():
            logger.info("Microservicio WhatsApp ya está corriendo en puerto 8000")
            self.running = True
            return True

        if not self.microservice_root.exists():
            logger.debug("Directorio whatsapp_service no encontrado; saltando auto-arranque")
            return False

        try:
            logger.info(f"Iniciando microservicio WhatsApp desde {self.microservice_root}...")
            # Usar creationflags=0x08 (CREATE_NO_WINDOW) en Windows para no mostrar consola
            creationflags = 0x08 if __import__("platform").system() == "Windows" else 0

            # Logs persistentes: nunca ocultar la salida del microservicio.
            log_path = self.log_file_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(log_path, "a", encoding="utf-8", errors="replace")

            # sys.executable -m uvicorn: no depende de que 'uvicorn' esté en
            # el PATH global — usa el mismo intérprete Python del POS.
            self.process = subprocess.Popen(
                self.launch_command(),
                cwd=self.microservice_root,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            logger.info(
                f"Microservicio lanzado (PID {self.process.pid}) — log: {log_path}"
            )

            # Esperar a que esté listo (hasta 30 segundos, backoff simple)
            for attempt in range(self.STARTUP_TIMEOUT_SECONDS):
                time.sleep(1)
                if self.is_healthy():
                    logger.info("Microservicio WhatsApp listo ✓")
                    self.running = True
                    return True

            logger.warning(
                "Microservicio no respondió en %d segundos. Revisa el log: %s",
                self.STARTUP_TIMEOUT_SECONDS, log_path,
            )
            return False

        except FileNotFoundError:
            logger.warning(
                "No se pudo lanzar uvicorn con %s -m uvicorn; instala uvicorn en "
                "el entorno del POS (pip install uvicorn).", sys.executable,
            )
            return False
        except Exception as exc:
            logger.warning(f"No se pudo iniciar microservicio: {exc}")
            return False

    def stop(self) -> None:
        """Detiene el microservicio si fue lanzado por este objeto."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("Microservicio detenido")
            except subprocess.TimeoutExpired:
                self.process.kill()
                logger.info("Microservicio forzadamente detenido")
            finally:
                self.process = None
                self.running = False

    def __enter__(self):
        """Context manager support."""
        self.try_start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.stop()


def launch_microservice_async(app_root: Path | None = None) -> None:
    """Inicia el microservicio en un thread daemon (no bloquea)."""
    def _launch():
        launcher = MicroserviceLauncher.get_instance(app_root)
        launcher.try_start()

    thread = threading.Thread(target=_launch, daemon=True)
    thread.start()

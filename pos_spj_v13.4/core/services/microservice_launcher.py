# core/services/microservice_launcher.py
"""Auto-arranque del microservicio WhatsApp si no está corriendo."""
from __future__ import annotations

import logging
import subprocess
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

            self.process = subprocess.Popen(
                ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
                cwd=self.microservice_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            logger.info(f"Microservicio lanzado (PID {self.process.pid})")

            # Esperar a que esté listo (hasta 10 segundos)
            for attempt in range(10):
                time.sleep(1)
                if self.is_healthy():
                    logger.info("Microservicio WhatsApp listo ✓")
                    self.running = True
                    return True

            logger.warning("Microservicio no respondió en 10 segundos")
            return False

        except FileNotFoundError:
            logger.debug("uvicorn no encontrado; microservicio no iniciado automáticamente")
            logger.info("Para usar el microservicio, ejecuta manualmente:")
            logger.info("  cd whatsapp_service && uvicorn main:app --port 8000")
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

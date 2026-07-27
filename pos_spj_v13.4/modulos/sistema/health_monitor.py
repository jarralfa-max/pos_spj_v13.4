
# modulos/sistema/health_monitor.py — SPJ POS v6.1
# Monitor de salud del sistema — nunca crashea el POS.
from __future__ import annotations
import os, logging, sqlite3
from datetime import datetime
from repositories.system_health_repository import SystemHealthRepository
try:
    from modulos.sistema.backup_engine import _get_db_path as _hm_get_db_path
except Exception:
    try:
        from core.db.connection import DB_PATH as _HM_DB_PATH
        def _hm_get_db_path(): return _HM_DB_PATH
    except Exception:
        def _hm_get_db_path(): return "spj_pos_database.db" 

logger = logging.getLogger("spj.health")


def get_system_health() -> dict:
    """Retorna métricas del sistema. Seguro — nunca eleva excepciones."""
    health = {
        "timestamp":     datetime.now().isoformat(),
        "db_size_mb":    0.0,
        "db_ok":         False,
        "error_count_24h": 0,
        "pending_sync":  0,
        "cpu_pct":       None,
        "mem_mb":        None,
        "disk_free_gb":  None,
        "warnings":      [],
    }
    # DB size
    try:
        health["db_size_mb"] = round(os.path.getsize(_hm_get_db_path()) / 1_048_576, 2)
        health["db_ok"] = True
    except Exception as e:
        health["warnings"].append(f"DB inaccessible: {e}")

    repo = SystemHealthRepository()

    # DB connectivity (el SQL vive en el repositorio)
    if repo.ping():
        health["db_ok"] = True
    else:
        health["db_ok"] = False
        health["warnings"].append("DB error: sin conexión")

    # Error count last 24h
    try:
        health["error_count_24h"] = repo.error_count_24h()
        if health["error_count_24h"] > 50:
            health["warnings"].append(f"Alto número de errores: {health['error_count_24h']}")
    except Exception:
        pass

    # Pending sync events
    try:
        health["pending_sync"] = repo.pending_sync_count()
        if health["pending_sync"] > 500:
            health["warnings"].append(f"Muchos eventos sin sincronizar: {health['pending_sync']}")
    except Exception:
        pass

    # Hardware stats (optional psutil)
    try:
        import psutil
        health["cpu_pct"]     = psutil.cpu_percent(interval=0.1)
        health["mem_mb"]      = round(psutil.virtual_memory().used / 1_048_576, 1)
        health["disk_free_gb"] = round(psutil.disk_usage(os.path.dirname(_hm_get_db_path())).free / 1_073_741_824, 2)
        if health["disk_free_gb"] < 1.0:
            health["warnings"].append(f"Poco espacio en disco: {health['disk_free_gb']:.2f} GB libre")
    except ImportError:
        pass
    except Exception as e:
        logger.debug("psutil error: %s", e)

    health["status"] = "OK" if not health["warnings"] else "WARNING"
    return health


def get_recent_errors(limit: int = 50) -> list:
    return SystemHealthRepository().recent_errors(limit)

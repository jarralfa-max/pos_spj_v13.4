# sync/conflict_resolver.py — SPJ POS v13.3
"""
Resolución de conflictos multi-sucursal con validación de dominio.

CAMBIOS v13.3 vs v13.2:
  - __init__ acepta lista de DomainValidator
  - resolve() ejecuta validadores DESPUÉS de la resolución genérica
  - Si un validador rechaza → MANUAL_REVIEW
  - Backward compatible: sin validadores, funciona igual que v13.2

v13.2 (preservado): Domain-aware — aplica política diferente según la tabla:
  ADDITIVE_TABLES   — inventario, caja: aplica DELTA, no sobreescribe estado
  LAST_WRITE_TABLES — clientes, productos: LWW por device_version
  SERVER_AUTH_TABLES — ventas, pagos: el servidor siempre gana
  DEFAULT           — LWW por device_version
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("spj.conflict_resolver")

# ── Clasificación de tablas (sin cambio) ──────────────────────────────────────
ADDITIVE_TABLES = frozenset({
    "movimientos_inventario", "inventory_movements", "branch_inventory",
    "caja_operations", "movimientos_caja", "detalles_venta",
    "lotes", "movimientos_lote",
})
SERVER_AUTH_TABLES = frozenset({
    "ventas", "ordenes_compra", "ordenes_compra_items",
    "compras", "detalles_compra",
})
LAST_WRITE_TABLES = frozenset({
    "clientes", "productos", "configuraciones",
    "proveedores", "usuarios",
})


class ConflictResolver:
    """
    Resuelve conflictos entre versiones local y remota de un registro.

    v13.3: Acepta validadores de dominio opcionales.

    El método resolve() retorna:
      - dict : payload resuelto para aplicar
      - None : conflicto requiere revisión manual (guardado en sync_conflicts)
    """

    SERVER_AUTHORITATIVE = "SERVER_AUTHORITATIVE"
    LAST_WRITE_WINS      = "LAST_WRITE_WINS"
    MANUAL_REVIEW        = "MANUAL_REVIEW"

    def __init__(self, db, validators: Optional[List] = None):
        self.db = db
        self._validators = validators or []

    # ── Punto de entrada ──────────────────────────────────────────────────────

    def resolve(
        self,
        event_id:       str,
        tabla:          str,
        local_payload:  dict,
        remote_payload: dict,
        policy:         str = None,
    ) -> Optional[dict]:
        """
        Resuelve el conflicto según el dominio de la tabla.
        Retorna el payload ganador, o None si requiere revisión manual.
        """
        # Override explícito de política
        if policy == self.SERVER_AUTHORITATIVE:
            resolution = remote_payload
            self._log(event_id, tabla, "SERVER_AUTH_override", resolution)
            return self._validate_domain(event_id, tabla, resolution,
                                          local_payload, remote_payload)

        # Dispatch por dominio (sin cambio respecto a v13.2)
        if tabla in ADDITIVE_TABLES:
            resolution = self._resolve_additive(local_payload, remote_payload)
            strategy = "ADDITIVE"
        elif tabla in SERVER_AUTH_TABLES:
            resolution = remote_payload
            strategy = "SERVER_AUTH"
        elif tabla in LAST_WRITE_TABLES or policy == self.LAST_WRITE_WINS:
            resolution = self._resolve_lww(local_payload, remote_payload)
            strategy = "LWW"
        else:
            resolution = self._resolve_lww(local_payload, remote_payload)
            strategy = "LWW_default"

        self._log(event_id, tabla, strategy, resolution)

        # v13.3: Validación de dominio post-resolución
        return self._validate_domain(
            event_id, tabla, resolution, local_payload, remote_payload
        )

    # ── Validación de dominio (NUEVO v13.3) ───────────────────────────────────

    def _validate_domain(
        self,
        event_id: str,
        tabla: str,
        resolution: dict,
        local_payload: dict,
        remote_payload: dict,
    ) -> Optional[dict]:
        """
        Ejecuta validadores de dominio sobre la resolución.
        Si alguno rechaza, escala a MANUAL_REVIEW y retorna None.
        """
        for validator in self._validators:
            try:
                error = validator.validate(
                    tabla, resolution, local_payload, remote_payload
                )
            except Exception as e:
                logger.error(
                    "Validator %s crashed: %s",
                    type(validator).__name__, e,
                )
                continue  # validator crash no bloquea sync

            if error:
                logger.warning(
                    "Validator %s rechazó [%s] tabla=%s: %s",
                    type(validator).__name__,
                    event_id[:8] if event_id else "?",
                    tabla,
                    error,
                )
                self.save_manual_conflict(
                    event_id, tabla, local_payload, remote_payload,
                    razon=f"DOMAIN_VALIDATION:{type(validator).__name__}: {error}",
                )
                return None

        return resolution

    # ── Estrategias por dominio (sin cambio respecto a v13.2) ─────────────────

    def _resolve_additive(self, local: dict, remote: dict) -> dict:
        result = dict(local)
        NUMERIC_DELTA_FIELDS = {
            "cantidad", "existencia", "stock", "quantity",
            "monto", "importe", "total", "saldo",
            "puntos", "balance",
        }
        for key, remote_val in remote.items():
            if key in NUMERIC_DELTA_FIELDS and isinstance(remote_val, (int, float)):
                local_val = float(local.get(key, 0))
                remote_val_f = float(remote_val)
                local_base = float(local.get(f"_{key}_base", local_val))
                remote_delta = remote_val_f - local_base
                result[key] = round(local_val + remote_delta, 6)
            else:
                result[key] = (
                    remote_val if self._remote_wins(local, remote)
                    else local.get(key, remote_val)
                )
        return result

    def _resolve_lww(self, local: dict, remote: dict) -> dict:
        return remote if self._remote_wins(local, remote) else local

    def _remote_wins(self, local: dict, remote: dict) -> bool:
        r_dv = int(remote.get("device_version", 0))
        l_dv = int(local.get("device_version", 0))
        if r_dv != l_dv:
            return r_dv > l_dv
        r_ts = remote.get("updated_at", "")
        l_ts = local.get("updated_at", "")
        if r_ts and l_ts:
            return str(r_ts) >= str(l_ts)
        return True

    # ── Registro de conflictos manuales (sin cambio) ──────────────────────────

    def _log(self, event_id, tabla, policy_applied, resolution):
        logger.debug(
            "Conflict resolved [%s] tabla=%s policy=%s",
            event_id[:8] if event_id else "?", tabla, policy_applied,
        )

    def save_manual_conflict(
        self,
        event_id:       str,
        tabla:          str,
        local_payload:  dict,
        remote_payload: dict,
        razon:          str = "MANUAL_REVIEW",
    ) -> None:
        try:
            self.db.execute("""
                INSERT OR IGNORE INTO sync_conflicts
                    (id, event_id, conflict_type,
                     local_version, remote_version,
                     remote_hash, computed_hash,
                     resolved, created_at)
                VALUES (lower(hex(randomblob(16))),?,?,?,?,?,?,0,?)
            """, (
                event_id,
                razon[:200],
                int(local_payload.get("device_version", 0)),
                int(remote_payload.get("device_version", 0)),
                _sha256(remote_payload),
                _sha256(local_payload),
                datetime.now(timezone.utc).isoformat(),
            ))
            try:
                self.db.commit()
            except Exception:
                pass
            logger.warning(
                "Conflicto guardado: event_id=%s tabla=%s razon=%s",
                event_id[:8] if event_id else "?", tabla, razon[:80],
            )
        except Exception as e:
            logger.error("save_manual_conflict: %s", e)


def _sha256(obj) -> str:
    import hashlib
    raw = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

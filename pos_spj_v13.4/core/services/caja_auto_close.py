# core/services/caja_auto_close.py
"""Auto-cierre de turnos de caja abiertos (medianoche) por la ruta canónica.

Remediación D1 paso 2c. Antes el scheduler cerraba turnos vía CierreCajaService
consultando `turno_actual`, un tracker legacy que en producción nadie abre (su
único escritor, CierreCajaService.abrir_turno, no se llama) → el auto-cierre era
un no-op. Los turnos reales viven en `turnos_caja` (abiertos por la UI vía
OpenCashShiftUseCase). Este helper los cierra por la ruta canónica de corte Z
(GenerateZCutUseCase → finance_service.generar_corte_z), que desde 2b registra
`cierres_caja` y postea el asiento de diferencia.

Es un cierre "a ciegas" (efectivo_fisico=0): sólo formaliza el cierre del turno
para que el día siguiente arranque limpio; la diferencia resultante refleja el
efectivo no contado.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.caja.auto_close")

_MOTIVO_DEFAULT = "Cierre automático por sistema — medianoche"


def auto_close_open_shifts(db, generate_z_cut_uc, motivo: str = _MOTIVO_DEFAULT) -> list:
    """Cierra todos los turnos abiertos en `turnos_caja` vía la ruta canónica.

    Devuelve la lista de `turno_id` cerrados con éxito. No lanza: cada turno se
    cierra de forma independiente y los errores se registran.
    """
    if generate_z_cut_uc is None:
        logger.warning("auto_close_open_shifts: GenerateZCutUseCase no disponible")
        return []

    from backend.application.commands.cash_register_commands import GenerateZCutCommand
    from backend.shared.ids import new_uuid

    try:
        rows = db.execute(
            "SELECT id, sucursal_id, cajero FROM turnos_caja WHERE estado='abierto'"
        ).fetchall()
    except Exception as e:
        logger.warning("auto_close_open_shifts: no se pudieron leer turnos abiertos: %s", e)
        return []

    cerrados: list = []
    for row in rows:
        turno_id = row[0]
        suc_id = row[1]
        cajero = (row[2] if len(row) > 2 else None) or "SISTEMA"
        try:
            generate_z_cut_uc.execute(GenerateZCutCommand(
                operation_id=new_uuid(),
                branch_id=str(suc_id),
                user_name=cajero,
                payload={"efectivo_fisico": 0.0, "observaciones": motivo},
            ))
            cerrados.append(str(turno_id))
            logger.warning("Turno %s (sucursal %s) cerrado automáticamente a medianoche",
                           turno_id, suc_id)
        except Exception as e_row:
            logger.warning("auto_close turno %s (sucursal %s): %s", turno_id, suc_id, e_row)
    return cerrados

"""266 — tolerancias de conciliación de facturas de proveedor.

QUÉ PASABA, MEDIDO (2026-09-18, sobre una copia de la base real)
-----------------------------------------------------------------
`ProcurementToleranceSettingsQueryService` exige las claves
`procurement.tolerance.{quantity,price,tax}.default` en `configuraciones` y,
si faltan, lanza `LookupError` ("Falta configuración canónica de tolerancia").
**Nadie las sembraba** — ni una migración, ni una prueba. La composición real
(`enterprise_routes.py`) inyecta ese servicio en la conciliación, así que en la
base real **conciliar CUALQUIER factura reventaba** con "Error inesperado; revise
el log", y ninguna factura podía llegar a cuenta por pagar: la cadena
factura → conciliación → CxP estaba muerta en producción.

Las pruebas no lo veían: arman `MatchSupplierInvoiceUseCase` SIN el servicio de
tolerancias, y entonces usa `Tolerance(0)` por omisión.

VALORES — decisión del usuario: exacto, 0 % en cantidad, precio e impuesto
-------------------------------------------------------------------------
Cualquier diferencia queda para que otro usuario la libere. Es lo que las
pruebas ya daban por bueno. El servicio admite además claves por proveedor
(`procurement.tolerance.<tipo>.supplier.<id>`) y por naturaleza, que tienen
prioridad sobre éstas.

`INSERT OR IGNORE`: si un administrador ya fijó un valor, no se pisa.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.266")

DEFAULTS = {
    "procurement.tolerance.quantity.default": (
        "0", "Tolerancia (%) de cantidad al conciliar facturas de proveedor"),
    "procurement.tolerance.price.default": (
        "0", "Tolerancia (%) de precio al conciliar facturas de proveedor"),
    "procurement.tolerance.tax.default": (
        "0", "Tolerancia (%) de impuesto al conciliar facturas de proveedor"),
}


def _columns(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(configuraciones)").fetchall()}


def run(conn) -> None:
    columnas = _columns(conn)
    if not {"clave", "valor"} <= columnas:
        logger.info("266: `configuraciones` no tiene la forma clave/valor; nada que sembrar.")
        return
    extra = [c for c in ("tipo", "grupo", "descripcion") if c in columnas]
    sembradas = 0
    for clave, (valor, descripcion) in DEFAULTS.items():
        campos = ["clave", "valor", *extra]
        valores = {"clave": clave, "valor": valor, "tipo": "decimal",
                   "grupo": "compras", "descripcion": descripcion}
        marcadores = ",".join("?" * len(campos))
        sembradas += conn.execute(
            f"INSERT OR IGNORE INTO configuraciones ({','.join(campos)}) VALUES ({marcadores})",
            tuple(valores[c] for c in campos)).rowcount or 0
    conn.commit()
    logger.info("266: %s tolerancias de conciliación sembradas.", sembradas)


up = run

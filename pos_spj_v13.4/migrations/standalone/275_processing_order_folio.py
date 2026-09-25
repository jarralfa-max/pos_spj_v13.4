"""275 — Folio humano de las órdenes de procesamiento (decisión del usuario,
2026-09-24): ``OP-<código de sucursal>-00001``, consecutivo por sucursal.

El código de la sucursal ya existía en Configuración → Empresa y sucursales
(`branch_profiles.code`, único); no se duplica en `sucursales`.

1. Toda sucursal sin perfil recibe uno MÍNIMO con un código inicial derivado
   del nombre (3 letras, sin acentos, único: CEN, CEN2…). Se cambia después
   en Configuración.
2. `processing_orders.folio` (+ índice único).
3. Las órdenes existentes reciben folio en su orden de creación, por sucursal,
   y el contador (`document_number_sequences`, prefijo ``OP-<código>``) queda
   en el último número usado para que las nuevas continúen.

Idempotente: sólo toca lo que falta.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.275")

DIGITS = 5


def _existe(conn, tabla: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (tabla,)).fetchone() is not None


def _columnas(conn, tabla: str) -> set[str]:
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{tabla}")').fetchall()}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_code(nombre: str, usados: set[str]) -> str:
    """3 letras del nombre, sin acentos; si ya existe, se numera (CEN, CEN2…)."""
    plano = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    letras = re.sub(r"[^A-Za-z]", "", plano).upper()
    base = (letras[:3] or "SUC").ljust(3, "X")
    codigo, n = base, 1
    while codigo in usados:
        n += 1
        codigo = f"{base}{n}"
    usados.add(codigo)
    return codigo


def _profiles_for_branches_without_one(conn) -> int:
    if not (_existe(conn, "sucursales") and _existe(conn, "branch_profiles")):
        return 0
    usados = {str(r[0]).upper() for r in conn.execute("SELECT code FROM branch_profiles")}
    creados = 0
    for branch_id, nombre in conn.execute(
            "SELECT s.id, s.nombre FROM sucursales s WHERE NOT EXISTS"
            " (SELECT 1 FROM branch_profiles b WHERE b.branch_id = s.id)"
            " ORDER BY s.fecha_alta, s.id").fetchall():
        codigo = derive_code(str(nombre or ""), usados)
        ahora = _ahora()
        try:
            conn.execute(
                "INSERT INTO branch_profiles (id, branch_id, code, name, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (branch_id, branch_id, codigo, str(nombre or codigo), ahora, ahora))
            creados += 1
        except Exception:  # noqa: BLE001 — sucursal con identidad no canónica: se informa
            usados.discard(codigo)
            logger.warning("275: la sucursal %s no pudo recibir perfil/código", branch_id)
    return creados


def _folio_column(conn) -> None:
    if "folio" not in _columnas(conn, "processing_orders"):
        conn.execute("ALTER TABLE processing_orders ADD COLUMN folio TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_orders_folio"
                 " ON processing_orders(folio) WHERE folio IS NOT NULL")


def _backfill_folios(conn) -> tuple[int, list[str]]:
    if not _existe(conn, "branch_profiles"):
        return 0, []
    asignados, sin_codigo = 0, []
    sucursales = [r[0] for r in conn.execute(
        "SELECT DISTINCT branch_id FROM processing_orders WHERE folio IS NULL").fetchall()]
    for branch_id in sucursales:
        fila = conn.execute("SELECT code FROM branch_profiles WHERE branch_id=?",
                            (branch_id,)).fetchone()
        if not fila or not fila[0]:
            sin_codigo.append(branch_id)
            continue
        prefijo = f"OP-{str(fila[0]).strip().upper()}"
        usados = [int(r[0].rsplit("-", 1)[1]) for r in conn.execute(
            "SELECT folio FROM processing_orders WHERE folio LIKE ?", (f"{prefijo}-%",))
            if r[0] and r[0].rsplit("-", 1)[1].isdigit()]
        numero = max(usados, default=0)
        for (orden_id,) in conn.execute(
                "SELECT id FROM processing_orders WHERE branch_id=? AND folio IS NULL"
                " ORDER BY created_at, id", (branch_id,)).fetchall():
            numero += 1
            conn.execute("UPDATE processing_orders SET folio=? WHERE id=?",
                         (f"{prefijo}-{numero:0{DIGITS}d}", orden_id))
            asignados += 1
        _align_sequence(conn, prefijo, numero)
    return asignados, sin_codigo


def _align_sequence(conn, prefijo: str, ultimo: int) -> None:
    if not _existe(conn, "document_number_sequences"):
        return
    fila = conn.execute("SELECT id, current_value FROM document_number_sequences WHERE prefix=?",
                        (prefijo,)).fetchone()
    ahora = _ahora()
    if fila is None:
        conn.execute(
            "INSERT INTO document_number_sequences (id, prefix, reset_policy, period_key,"
            " current_value, created_at, updated_at) VALUES (?,?,'NEVER','',?,?,?)",
            (new_uuid(), prefijo, ultimo, ahora, ahora))
    elif int(fila[1] or 0) < ultimo:
        conn.execute("UPDATE document_number_sequences SET current_value=?, updated_at=?"
                     " WHERE id=?", (ultimo, ahora, fila[0]))


def run(conn) -> None:
    if not _existe(conn, "processing_orders"):
        logger.info("275: sin Procesamiento; nada que hacer.")
        return
    perfiles = _profiles_for_branches_without_one(conn)
    _folio_column(conn)
    asignados, sin_codigo = _backfill_folios(conn)
    conn.commit()
    logger.info("275: perfiles con código creados=%s, folios asignados=%s, sucursales sin "
                "código=%s", perfiles, asignados, sin_codigo or "ninguna")


up = run

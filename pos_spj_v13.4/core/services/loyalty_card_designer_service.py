# core/services/loyalty_card_designer_service.py
"""
LoyaltyCardDesignerService — escrituras/lecturas del diseñador de tarjetas de
fidelidad (Remediación F).

Ruta canónica: LoyaltyCardDesigner (UI) → LoyaltyCardDesignerService → DB. Extrae
el SQL embebido en modulos/loyalty_card_designer.py: plantilla, pregeneración de
tarjetas, lotes PDF, administración de tarjetas y lookup de clientes. El SQL se
preserva EXACTO salvo un bugfix de identidad born-clean.

Bugfix (born-clean): el INSERT de lotes_tarjetas_pdf omitía `id`
(TEXT PRIMARY KEY sin default) → filas con id=NULL. El servicio genera new_uuid().

Deuda conocida (NO tocada aquí, se preserva el comportamiento actual): varias
consultas referencian columnas legacy que no existen en el esquema born-clean
(`codigo`, `puntos`, `fecha_emision`), por lo que ya fallan en runtime (la UI las
envuelve en try/except). Migrarlas a `codigo_qr`/`puntos_actuales` es un cambio
semántico que corresponde a una tarea aparte.
"""
from __future__ import annotations

import json
import logging
import uuid

logger = logging.getLogger("spj.services.loyalty_card_designer")


class LoyaltyCardDesignerService:
    def __init__(self, db):
        self.db = db

    # ── Plantilla (tabla configuraciones) ───────────────────────────────────────
    def obtener_plantilla(self):
        return self.db.execute(
            "SELECT valor FROM configuraciones WHERE clave='loyalty_card_plantilla'"
        ).fetchone()

    def guardar_plantilla(self, valor_json: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)",
            ("loyalty_card_plantilla", valor_json))
        self.db.commit()

    # ── Pregeneración de tarjetas ───────────────────────────────────────────────
    def listar_tarjetas_pregeneradas(self, nivel: str, sin_asignar: bool, cant: int) -> list:
        """SELECT de tarjetas pregeneradas disponibles. Devuelve filas crudas para
        preservar la semántica `if rows:` de la UI."""
        query = """SELECT COALESCE(codigo_qr, codigo, numero) as card_code, nivel
                   FROM tarjetas_fidelidad
                   WHERE COALESCE(activa, CASE estado WHEN 'disponible' THEN 1
                         WHEN 'activa' THEN 1 ELSE 0 END, 1) = 1"""
        params = []
        if nivel != "Todos":
            query += " AND nivel=?"; params.append(nivel)
        if sin_asignar:
            query += " AND (id_cliente IS NULL OR id_cliente=0)"
        query += f" LIMIT {cant}"
        return self.db.execute(query, params).fetchall()

    def generar_tarjetas_pregeneradas(self, cant: int, nivel_real: str) -> list:
        """Genera hasta min(cant,500) tarjetas pregeneradas (INSERT OR IGNORE con
        variantes de compatibilidad de esquema) y devuelve la lista de dicts."""
        from backend.shared.ids import new_uuid
        n = min(cant, 500)
        cards = []
        try:
            for _ in range(n):
                codigo = f"SPJ{uuid.uuid4().hex[:8].upper()}"
                # Identidad UUIDv7 explícita (REGLA CERO): el id no se delega a
                # autoincrement. Insert con ambos nombres de columna por compat.
                try:
                    self.db.execute(
                        "INSERT OR IGNORE INTO tarjetas_fidelidad"
                        "(id, codigo_qr, codigo, nivel, estado, activa, es_pregenerada) "
                        "VALUES(?,?,?,?,?,1,1)",
                        (new_uuid(), codigo, codigo, nivel_real, 'disponible'))
                except Exception:
                    # Fallback: try with just one column variant
                    try:
                        self.db.execute(
                            "INSERT OR IGNORE INTO tarjetas_fidelidad"
                            "(id, codigo_qr, nivel, estado, es_pregenerada) "
                            "VALUES(?,?,?,?,1)",
                            (new_uuid(), codigo, nivel_real, 'disponible'))
                    except Exception:
                        self.db.execute(
                            "INSERT OR IGNORE INTO tarjetas_fidelidad"
                            "(id, codigo, nivel, activa, es_pregenerada) "
                            "VALUES(?,?,?,1,1)",
                            (new_uuid(), codigo, nivel_real))
                cards.append({"codigo": codigo, "nivel": nivel_real})
            self.db.commit()
        except Exception as e:
            logger.warning("generate cards: %s", e)
        return cards

    # ── Lotes PDF ───────────────────────────────────────────────────────────────
    def registrar_lote(self, cantidad: int, nivel: str, ruta_pdf: str,
                       plantilla_json: str, usuario: str) -> str:
        """Registra un lote PDF. Bugfix born-clean: se genera `id` explícito
        (antes el INSERT lo omitía → id=NULL)."""
        from backend.shared.ids import new_uuid
        lote_id = new_uuid()
        self.db.execute(
            "INSERT INTO lotes_tarjetas_pdf(id,cantidad,nivel,ruta_pdf,plantilla,usuario) "
            "VALUES(?,?,?,?,?,?)",
            (lote_id, cantidad, nivel, ruta_pdf, plantilla_json, usuario))
        self.db.commit()
        return lote_id

    def listar_historial_lotes(self) -> list:
        return self.db.execute(
            "SELECT created_at,cantidad,nivel,ruta_pdf,id FROM lotes_tarjetas_pdf "
            "ORDER BY created_at DESC LIMIT 100"
        ).fetchall()

    # ── Administración de tarjetas ──────────────────────────────────────────────
    def listar_tarjetas(self) -> list:
        return self.db.execute("""
            SELECT COALESCE(t.codigo_qr, t.codigo, t.numero) as card_code,
                   t.nivel,
                   COALESCE(c.nombre,'Sin asignar'),
                   COALESCE(t.puntos_actuales, t.puntos, 0),
                   CASE
                     WHEN t.activa=1 OR t.estado IN ('disponible','activa') THEN 'Activa'
                     WHEN t.activa=0 OR t.estado='bloqueada' THEN 'Bloqueada'
                     ELSE COALESCE(t.estado, 'Activa')
                   END,
                   COALESCE(t.fecha_emision, t.fecha_creacion, '')
            FROM tarjetas_fidelidad t
            LEFT JOIN clientes c ON c.id=t.id_cliente
            ORDER BY COALESCE(t.puntos_actuales, t.puntos, 0) DESC LIMIT 300
        """).fetchall()

    def ajustar_puntos(self, codigo: str, puntos: int) -> None:
        self.db.execute("UPDATE tarjetas_fidelidad SET puntos=? WHERE codigo=?", (puntos, codigo))
        self.db.commit()

    def cambiar_nivel(self, codigo: str, nuevo: str) -> None:
        self.db.execute("UPDATE tarjetas_fidelidad SET nivel=? WHERE codigo=?", (nuevo, codigo))
        self.db.commit()

    def bloquear_tarjeta(self, codigo: str) -> None:
        self.db.execute("UPDATE tarjetas_fidelidad SET activa=0 WHERE codigo=?", (codigo,))
        self.db.commit()

    def listar_clientes_lookup(self) -> list:
        return self.db.execute(
            "SELECT id,nombre FROM clientes WHERE activo=1 ORDER BY nombre LIMIT 300"
        ).fetchall()

    def asignar_tarjeta_nueva(self, cliente_id, codigo: str, nivel: str) -> None:
        from backend.shared.ids import new_uuid
        self.db.execute(
            "INSERT OR IGNORE INTO tarjetas_fidelidad(id,id_cliente,codigo,nivel,activa) "
            "VALUES(?,?,?,?,1)", (new_uuid(), cliente_id, codigo, nivel))
        self.db.commit()

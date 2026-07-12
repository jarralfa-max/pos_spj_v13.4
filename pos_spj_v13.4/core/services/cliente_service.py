# core/services/cliente_service.py
"""Servicio de administración para el módulo Clientes."""
from __future__ import annotations
import logging
import re
import sqlite3
from typing import Dict, List, Optional

from repositories.cliente_repository import ClienteRepository

logger = logging.getLogger("spj.service.clientes")


class ClienteService:
    """Fachada para operaciones de clientes. UI llama solo a este servicio."""

    def __init__(self, db):
        self._repo = ClienteRepository(db)

    # ── Consultas ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Devuelve estadísticas agregadas: total, activos, con tarjeta, puntos."""
        return self._repo.get_stats_aggregate()

    def get_filtered(self, filtro: str = "todos") -> List[Dict]:
        """Get clientes with state filter: activos, inactivos, todos."""
        return self._repo.get_filtered(filtro)

    def search(self, termino: str, filtro: str = "todos") -> List[Dict]:
        """Search clientes by name, phone, id or QR."""
        if not termino.strip():
            return self.get_filtered(filtro)
        return self._repo.buscar_por_termino(termino.strip(), filtro)

    def get_by_id(self, cliente_id: int) -> Optional[Dict]:
        """Get complete client data by ID."""
        return self._repo.get_by_id(cliente_id)

    def get_historial(self, cliente_id: int) -> List[Dict]:
        """Get purchase history for a client."""
        return self._repo.get_historial_compras(cliente_id)

    def get_movimientos_puntos(self, cliente_id: int) -> List[Dict]:
        """Get loyalty points movements for a client."""
        return self._repo.get_movimientos_puntos(cliente_id)

    # ── Mutaciones ────────────────────────────────────────────────────────

    def crear(self, nombre: str, telefono: str = "", email: str = "",
              direccion: str = "", notas: str = "") -> str:
        """Create a new client (returns UUIDv7 id)."""
        return self._repo.crear(nombre, telefono, email, direccion, notas)

    def actualizar(self, cliente_id: int, **campos) -> bool:
        """Update client fields."""
        return self._repo.actualizar(cliente_id, **campos)

    def dar_de_baja(self, cliente_id: int) -> bool:
        """Soft-delete: mark inactive, preserve history."""
        return self._repo.dar_de_baja(cliente_id)

    def actualizar_puntos(self, cliente_id: int, nuevos_puntos: float) -> bool:
        """Update loyalty points balance."""
        return self._repo.actualizar_puntos(cliente_id, nuevos_puntos)

    # ── Alta/edición desde el formulario (Remediación D) ──────────────────────
    #  Ruta canónica: DialogoCliente captura un DTO y delega aquí. El diálogo NO
    #  ejecuta SQL/commit/publish. Preserva la lógica original: intento vía UC con
    #  fallback a SQL, deduplicación con confirmación, parsing de tarjeta y evento.

    @staticmethod
    def parse_tarjeta(tarjeta_raw: str) -> str:
        """Normaliza el ID de tarjeta capturado (prefijos TF-/TAR-/CARD-/CLT-)."""
        tarjeta_raw = (tarjeta_raw or "").strip()
        if not tarjeta_raw:
            return ""
        m = re.match(r'^(?:TF|TAR|CARD)-(.+)$', tarjeta_raw, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m2 = re.match(r'^CLT-(\d+)', tarjeta_raw, re.IGNORECASE)
        if m2:
            return m2.group(1)
        return tarjeta_raw

    def existe_similar(self, nombre, apellido, telefono) -> bool:
        row = self._repo.db.execute(
            "SELECT COUNT(*) FROM clientes "
            "WHERE nombre = ? AND COALESCE(apellido,'') = ? AND telefono = ?",
            (nombre, apellido or "", telefono)
        ).fetchone()
        return bool(row and row[0] > 0)

    def guardar_formulario(self, dto: dict, confirm_duplicate=None, uc_cliente=None) -> dict:
        """Crea o actualiza un cliente desde el DTO capturado por la UI.

        Retorna: {"ok": bool, "titulo": str, "mensaje": str, "created_id": str|None,
                  "error": str|None, "cancelled": bool}. `confirm_duplicate()` -> bool
        se invoca sólo en alta con posible duplicado (interacción UI vía callback).
        """
        db = self._repo.db
        is_edit = bool(dto.get("is_edit"))
        cliente_id = dto.get("cliente_id")
        nombre = dto.get("nombre", "")
        apellido = dto.get("apellido") or ""
        telefono = dto.get("telefono") or ""
        limite_credito = dto.get("limite_credito", 0.0)

        # 1) Intento vía caso de uso. Una respuesta not-ok corta el flujo; sólo una
        #    EXCEPCIÓN cae al fallback SQL (idéntico al diálogo original).
        if uc_cliente:
            try:
                from core.use_cases.cliente import DatosCliente
                datos = DatosCliente(
                    nombre=f"{nombre} {apellido}".strip(),
                    telefono=telefono,
                    allows_credit=(limite_credito > 0),
                    credit_limit=limite_credito,
                )
                if is_edit:
                    campos = {
                        'nombre': nombre, 'apellido': apellido, 'telefono': telefono,
                        'limite_credito': limite_credito, 'saldo': dto.get("saldo", 0.0),
                        'activo': dto.get("activo", 1),
                    }
                    result = uc_cliente.actualizar_cliente(cliente_id, campos, "sistema")
                else:
                    result = uc_cliente.crear_cliente(datos, 1, "sistema")
                if result.ok:
                    return {"ok": True, "titulo": "Éxito",
                            "mensaje": getattr(result, "mensaje", "") or "Guardado correctamente."}
                return {"ok": False, "error": getattr(result, "error", "") or "No se pudo guardar."}
            except Exception as e:
                logger.debug("UC cliente falló, fallback a SQL: %s", e)

        # 2) Fallback SQL directo.
        nombre_sql = nombre.strip()
        apellido_sql = apellido.strip() or None
        telefono_sql = (telefono or "").strip() or None
        puntos = dto.get("puntos", 0)
        nivel = (dto.get("nivel") or "").strip() or None
        descuento = dto.get("descuento", 0.0)
        saldo = dto.get("saldo", 0.0)
        activo = 1 if dto.get("activo", 1) else 0
        tarjeta_id = self.parse_tarjeta(dto.get("tarjeta_raw", ""))

        try:
            cursor = db.cursor()
            if is_edit:
                cursor.execute("""
                    UPDATE clientes
                    SET nombre = ?, apellido = ?, telefono = ?, puntos = ?, nivel_fidelidad = ?,
                        descuento = ?, saldo = ?, limite_credito = ?, activo = ?,
                        codigo_qr = CASE WHEN ? != '' THEN ? ELSE codigo_qr END
                    WHERE id = ?
                """, (nombre_sql, apellido_sql, telefono_sql, puntos, nivel, descuento, saldo,
                      limite_credito, activo, tarjeta_id, tarjeta_id, cliente_id))

                if tarjeta_id:
                    try:
                        cursor.execute("""
                            INSERT INTO tarjetas_fidelidad (codigo, id_cliente, nivel, activa, fecha_emision)
                            VALUES (?, ?, COALESCE(?, 'Bronce'), 1, datetime('now'))
                            ON CONFLICT(codigo) DO UPDATE SET id_cliente = ?, activa = 1
                        """, (tarjeta_id, cliente_id, nivel, cliente_id))
                    except Exception:
                        pass

                db.commit()
                try:
                    from core.events.event_bus import get_bus
                    get_bus().publish("CLIENTE_ACTUALIZADO", {"event_type": "CLIENTE_ACTUALIZADO"})
                except Exception:
                    pass
                return {"ok": True, "titulo": "Éxito",
                        "mensaje": "Cliente actualizado correctamente."}
            else:
                if self.existe_similar(nombre_sql, apellido_sql or "", telefono_sql):
                    if confirm_duplicate is not None and not confirm_duplicate():
                        return {"ok": False, "cancelled": True}

                from backend.shared.ids import new_uuid
                id_cliente = new_uuid()
                cursor.execute("""
                    INSERT INTO clientes (id, nombre, apellido, telefono, puntos, nivel_fidelidad,
                                        descuento, saldo, limite_credito, activo, codigo_qr)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (id_cliente, nombre_sql, apellido_sql, telefono_sql, puntos, nivel, descuento,
                      saldo, limite_credito, activo, tarjeta_id or None))

                if tarjeta_id:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO tarjetas_fidelidad
                                (codigo, id_cliente, nivel, activa, fecha_emision)
                            VALUES (?, ?, 'Bronce', 1, datetime('now'))
                        """, (tarjeta_id, id_cliente))
                    except Exception:
                        pass

                db.commit()
                return {"ok": True, "titulo": "Cliente creado",
                        "mensaje": f"ID: {id_cliente}", "created_id": id_cliente}

        except sqlite3.IntegrityError as e:
            db.rollback()
            return {"ok": False, "error": f"Error de integridad: {str(e)}", "kind": "integrity"}
        except sqlite3.Error as e:
            db.rollback()
            return {"ok": False, "error": f"Error en la base de datos: {str(e)}"}
        except Exception as e:
            db.rollback()
            return {"ok": False, "error": f"Error inesperado: {str(e)}"}

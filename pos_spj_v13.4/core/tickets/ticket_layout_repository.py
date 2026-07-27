from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .ticket_layout_config import TicketLayoutConfig

logger = logging.getLogger("spj.ticket_layout_repository")


class TicketLayoutRepository:
    """Single read/write gateway for thermal ticket layouts.

    The canonical store is ticket_layouts(layout_type, config_json).  Legacy
    configuraciones keys are read only as compatibility fallbacks for sale_ticket.
    """

    VALID_LAYOUT_TYPES = {"sale_ticket", "raffle_ticket"}

    def __init__(self, db_conn=None, config_service=None):
        self.db = db_conn
        self.config_service = config_service

    def _normalize_layout_type(self, layout_type: str = "sale_ticket") -> str:
        lt = str(layout_type or "sale_ticket").strip() or "sale_ticket"
        return lt if lt in self.VALID_LAYOUT_TYPES else "sale_ticket"

    def ensure_schema(self) -> None:
        # Plan B born-clean: ticket_layouts (id TEXT UUIDv7) vive en
        # migrations/m000_base_schema. El repositorio no emite DDL.
        return None

    def _table_columns(self, table: str) -> set[str]:
        if self.db is None:
            return set()
        try:
            return {str(r[1]) for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return set()

    def _table_exists(self, table: str) -> bool:
        if self.db is None:
            return False
        try:
            row = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            return bool(row)
        except Exception:
            return False

    def _get(self, key: str, default: str = "") -> str:
        if self.config_service is not None:
            v = self.config_service.get(key, default)
            return v if v not in (None, "") else default
        if self.db is None or not self._table_exists("configuraciones"):
            return default
        try:
            row = self.db.execute("SELECT valor FROM configuraciones WHERE clave=?", (key,)).fetchone()
            return row[0] if row and row[0] else default
        except Exception:
            return default

    def _set(self, key: str, value: str) -> None:
        if self.config_service is not None:
            self.config_service.set(key, value)
            return
        if self.db is None:
            return
        pass  # Plan B born-clean: schema canónico en migrations/ (DDL removido)
        self.db.execute("INSERT OR REPLACE INTO configuraciones(clave, valor) VALUES (?,?)", (key, value))
        try:
            self.db.commit()
        except Exception:
            pass

    def _row_to_dict(self, row) -> dict[str, Any]:
        if not row:
            return {}
        if isinstance(row, dict):
            return dict(row)
        try:
            return {k: row[k] for k in row.keys()}
        except Exception:
            return {
                "id": row[0], "layout_type": row[1], "nombre": row[2], "config_json": row[3],
                "activo": row[4], "created_at": row[5] if len(row) > 5 else None, "updated_at": row[6] if len(row) > 6 else None,
            }

    def get_active_layout_row(self, layout_type: str = "sale_ticket") -> Optional[dict[str, Any]]:
        if self.db is None:
            return None
        self.ensure_schema()
        lt = self._normalize_layout_type(layout_type)
        row = self.db.execute(
            """
            SELECT id, layout_type, nombre, config_json, activo, created_at, updated_at
              FROM ticket_layouts
             WHERE layout_type=? AND activo=1
             ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
             LIMIT 1
            """,
            (lt,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def _get_latest_layout_row(self, layout_type: str) -> Optional[dict[str, Any]]:
        if self.db is None:
            return None
        self.ensure_schema()
        row = self.db.execute(
            """
            SELECT id, layout_type, nombre, config_json, activo, created_at, updated_at
              FROM ticket_layouts
             WHERE layout_type=?
             ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
             LIMIT 1
            """,
            (self._normalize_layout_type(layout_type),),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def _cfg_from_row(self, row: dict[str, Any] | None) -> Optional[TicketLayoutConfig]:
        if not row:
            return None
        try:
            return TicketLayoutConfig.from_dict(json.loads(str(row.get("config_json") or "{}")))
        except Exception as exc:
            logger.warning("Layout inválido id=%s: %s", row.get("id"), exc)
            return None

    def _load_configuraciones_sale(self) -> Optional[TicketLayoutConfig]:
        raw = self._get("ticket_layout_config", "")
        if raw:
            try:
                return TicketLayoutConfig.from_dict(json.loads(raw))
            except Exception as exc:
                logger.warning("ticket_layout_config legacy inválido: %s", exc)
        return None

    def _load_legacy_sale(self) -> TicketLayoutConfig:
        legacy = {
            "ticket_paper_width": self._get("ticket_paper_width", "80"),
            "ticket_logo_width": self._get("ticket_logo_width", "150"),
            "ticket_logo_pos": self._get("ticket_logo_pos", "Centrado"),
            "ticket_qr_enabled": self._get("ticket_qr_enabled", "0"),
            "ticket_bc_enabled": self._get("ticket_bc_enabled", "0"),
        }
        return TicketLayoutConfig.from_legacy_config(legacy)

    def load(self, layout_type: str = "sale_ticket") -> TicketLayoutConfig:
        lt = self._normalize_layout_type(layout_type)
        cfg = self._cfg_from_row(self.get_active_layout_row(lt)) or self._cfg_from_row(self._get_latest_layout_row(lt))
        if cfg:
            return cfg
        if lt == "sale_ticket":
            cfg = self._load_configuraciones_sale()
            if cfg:
                self._copy_on_read(cfg, lt, "Migrado desde configuraciones")
                return cfg
            return self._load_legacy_sale()
        cfg = TicketLayoutConfig.for_layout_type(lt)
        self._copy_on_read(cfg, lt, "Boleto de sorteo")
        return cfg

    def _copy_on_read(self, cfg: TicketLayoutConfig, layout_type: str, nombre: str) -> None:
        if self.db is None:
            return
        try:
            if self._get_latest_layout_row(layout_type):
                return
            self.save(cfg, layout_type=layout_type, nombre=nombre)
        except Exception as exc:
            logger.debug("copy-on-read layout omitido: %s", exc)

    def save(self, cfg: TicketLayoutConfig | dict[str, Any], layout_type: str = "sale_ticket", nombre: str | None = None) -> None:
        lt = self._normalize_layout_type(layout_type)
        if not isinstance(cfg, TicketLayoutConfig):
            cfg = TicketLayoutConfig.from_dict(dict(cfg or {}))
        if lt == "raffle_ticket" and not cfg.block_order:
            cfg = TicketLayoutConfig.for_layout_type("raffle_ticket")
        raw = json.dumps(cfg.to_dict(), ensure_ascii=False)
        if self.db is None:
            if lt == "sale_ticket":
                self._set("ticket_layout_config", raw)
            return
        self.ensure_schema()
        self.db.execute("UPDATE ticket_layouts SET activo=0, updated_at=datetime('now') WHERE layout_type=?", (lt,))
        self.db.execute(
            """
            INSERT INTO ticket_layouts(layout_type, nombre, config_json, activo, updated_at)
            VALUES(?,?,?,?,datetime('now'))
            """,
            (lt, str(nombre or ("Ticket de venta" if lt == "sale_ticket" else "Boleto de sorteo")), raw, 1),
        )
        if lt == "sale_ticket":
            self._set("ticket_layout_config", raw)
        else:
            try:
                self.db.commit()
            except Exception:
                pass

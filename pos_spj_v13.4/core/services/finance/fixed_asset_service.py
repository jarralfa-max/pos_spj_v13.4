# core/services/finance/fixed_asset_service.py — SPJ ERP v13.4
"""
FixedAssetService — activos fijos idempotentes.

Opera sobre `fixed_assets` y `asset_depreciation_entries` (migración 083).
Coexiste con tabla legacy `activos` — no la reemplaza.

Política de capitalización:
  - Bienes con costo >= CAPITALIZATION_THRESHOLD se registran como activo fijo.
  - Bienes menores se registran como gasto operativo (no crean fixed_asset).
  - El caller decide el tratamiento; este servicio solo registra activos.

Reglas:
  - Idempotente por operation_id (UNIQUE en ambas tablas).
  - depreciate_asset() NO hace commit.
  - Un período por asset_id no puede tener más de una depreciación.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.fixed_asset")

CAPITALIZATION_THRESHOLD = 5_000.0  # MXN — política de capitalización


class FixedAssetService:
    """Activos fijos y depreciaciones."""

    def __init__(self, db, journal_service=None):
        from core.db.connection import wrap
        self._db = wrap(db)
        self._je = journal_service  # JournalEntryService

    # ── Registro de activo ────────────────────────────────────────────────────

    def register_asset_purchase(
        self,
        operation_id: str,
        asset_name: str,
        asset_type: str,
        acquisition_cost: float,
        acquisition_date: Optional[str] = None,
        useful_life_months: int = 60,
        depreciation_method: str = "straight_line",
        supplier_id: Optional[int] = None,
        source_module: str = "activos",
        source_id: Optional[int] = None,
        source_folio: str = "",
        financial_document_id: Optional[int] = None,
        treasury_movement_id: Optional[int] = None,
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Registra compra de activo fijo (idempotente por operation_id).

        Retorna: id del fixed_asset. 0 si tabla no disponible.
        """
        if not operation_id:
            return 0
        if acquisition_cost <= 0:
            logger.warning("register_asset op=%s: cost=%.2f inválido", operation_id, acquisition_cost)
            return 0

        try:
            existing = self._db.fetchone(
                "SELECT id FROM fixed_assets WHERE operation_id=?", (operation_id,)
            )
            if existing:
                logger.debug("fixed_assets: op_id=%s ya existe", operation_id)
                return existing["id"]  # UUIDv7 (sin cast)
        except Exception as exc:
            logger.debug("fixed_assets no disponible: %s", exc)
            return 0

        acq_date = acquisition_date or date.today().isoformat()
        try:
            from backend.shared.ids import new_uuid
            asset_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self._db.execute(
                """INSERT INTO fixed_assets
                       (id, asset_name, asset_type, acquisition_date, acquisition_cost,
                        current_value, accumulated_depreciation, depreciation_method,
                        useful_life_months, status, supplier_id, branch_id,
                        source_module, source_id, source_folio,
                        financial_document_id, treasury_movement_id,
                        operation_id, metadata_json)
                   VALUES (?,?,?,?,?,?,0.0,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    asset_id,
                    asset_name, asset_type, acq_date,
                    float(acquisition_cost), float(acquisition_cost),
                    depreciation_method, useful_life_months,
                    "active", supplier_id, branch_id,
                    source_module, source_id, source_folio,
                    financial_document_id, treasury_movement_id,
                    operation_id,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
        except Exception as exc:
            logger.warning("fixed_assets INSERT op=%s: %s", operation_id, exc)
            return 0

        # Journal: debe=activo_fijo / haber=caja_o_cxp
        if self._je and asset_id:
            credit = "130.1-cuentas_por_pagar" if financial_document_id else "110-caja"
            self._je.post_entry(
                operation_id=f"{operation_id}-JE",
                event_type="FIXED_ASSET_PURCHASED",
                source_module=source_module,
                source_id=source_id,
                source_folio=source_folio,
                debit_account="150-activos_fijos",
                credit_account=credit,
                amount=float(acquisition_cost),
                branch_id=branch_id,
                user=user,
                metadata={"asset_id": asset_id, "asset_name": asset_name},
            )

        return asset_id

    # ── Depreciación ──────────────────────────────────────────────────────────

    def depreciate_asset(
        self,
        asset_id: int,
        period: str,
        amount: Optional[float] = None,
        user: str = "sistema",
    ) -> int:
        """
        Registra depreciación mensual de un activo.

        Args:
            asset_id: id en fixed_assets
            period: 'YYYY-MM'
            amount: monto de depreciación (si None, calcula automático)

        Retorna: id de asset_depreciation_entries. 0 si ya existe (idempotente).
        NO crea treasury_movement (depreciación no mueve dinero).
        """
        op_id = f"dep-{asset_id}-{period}"
        try:
            existing = self._db.fetchone(
                "SELECT id FROM asset_depreciation_entries WHERE operation_id=?", (op_id,)
            )
            if existing:
                logger.debug("depreciation: asset=%s period=%s ya existe", asset_id, period)
                return existing["id"]  # UUIDv7 (sin cast)
        except Exception as exc:
            logger.debug("asset_depreciation_entries no disponible: %s", exc)
            return 0

        asset = self._get_asset(asset_id)
        if not asset:
            logger.warning("depreciate_asset: asset_id=%s no encontrado", asset_id)
            return 0

        dep_amount = amount if amount is not None else self._calc_monthly_depreciation(asset)
        if dep_amount <= 0:
            return 0

        # Journal entry: debe=depreciación_expense / haber=depreciación_acumulada
        je_id = 0
        if self._je:
            je_id = self._je.post_entry(
                operation_id=f"{op_id}-JE",
                event_type="FIXED_ASSET_DEPRECIATED",
                source_module="activos",
                source_id=asset_id,
                debit_account="640-depreciacion_expense",
                credit_account="155-depreciacion_acumulada",
                amount=dep_amount,
                user=user,
                metadata={"asset_id": asset_id, "period": period},
            )

        try:
            from backend.shared.ids import new_uuid
            entry_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self._db.execute(
                """INSERT INTO asset_depreciation_entries
                       (id, asset_id, period, amount, journal_entry_id, operation_id)
                   VALUES (?,?,?,?,?,?)""",
                (entry_id, asset_id, period, float(dep_amount), je_id, op_id),
            )
        except Exception as exc:
            logger.warning("depreciation INSERT asset=%s period=%s: %s", asset_id, period, exc)
            return 0

        # Update accumulated depreciation in fixed_assets
        try:
            self._db.execute(
                """UPDATE fixed_assets
                   SET accumulated_depreciation = COALESCE(accumulated_depreciation, 0) + ?,
                       current_value = MAX(0, current_value - ?),
                       updated_at = datetime('now')
                   WHERE id=?""",
                (dep_amount, dep_amount, asset_id),
            )
        except Exception:
            pass

        return entry_id

    def dispose_asset(
        self,
        asset_id: int,
        reason: str = "disposed",
        user: str = "sistema",
    ) -> bool:
        """Marca un activo como disposed/sold."""
        try:
            self._db.execute(
                "UPDATE fixed_assets SET status=?, updated_at=datetime('now') WHERE id=?",
                (reason, asset_id),
            )
            return True
        except Exception as exc:
            logger.warning("dispose_asset id=%s: %s", asset_id, exc)
            return False

    def get_asset_trace(self, asset_id: int) -> Dict:
        """Retorna activo + depreciaciones registradas."""
        asset = self._get_asset(asset_id)
        if not asset:
            return {}
        try:
            deps = self._db.fetchall(
                "SELECT * FROM asset_depreciation_entries WHERE asset_id=? ORDER BY period",
                (asset_id,),
            )
            asset["depreciaciones"] = [dict(d) for d in deps]
        except Exception:
            asset["depreciaciones"] = []
        return asset

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_asset(self, asset_id: int) -> Optional[Dict]:
        try:
            row = self._db.fetchone("SELECT * FROM fixed_assets WHERE id=?", (asset_id,))
            return dict(row) if row else None
        except Exception:
            return None

    def _calc_monthly_depreciation(self, asset: Dict) -> float:
        cost = float(asset.get("acquisition_cost", 0))
        months = int(asset.get("useful_life_months", 60)) or 60
        return round(cost / months, 2)

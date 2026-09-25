"""Persistencia de la definición productiva congelada de una orden.

Sólo INSERT: no existe `update` ni `delete` a propósito. Una orden tiene una
única foto, sellada al liberarse; si la definición en Productos cambia después,
la orden sigue ejecutando la foto.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
    InputRole,
    ProcessingRecipeSnapshot,
    SnapshotInput,
    SnapshotOutput,
)
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.shared.ids import new_uuid


def _txt(value) -> str | None:
    return None if value is None else str(value)


def _dec(value) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


class ProcessingRecipeSnapshotRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def add(self, snapshot: ProcessingRecipeSnapshot) -> None:
        if not snapshot.is_frozen:
            raise MeatProcessingInvariantError("Sólo se guarda una definición congelada")
        if self.get_by_order(snapshot.processing_order_id) is not None:
            raise MeatProcessingInvariantError(
                "La orden ya tiene su definición productiva congelada; no se reemplaza")
        self._conn.execute(
            "INSERT INTO processing_recipe_snapshots (id, operation_id, processing_order_id,"
            " process_type, target_product_id, recipe_version_id, cutting_scheme_version_id,"
            " yield_profile_version_id, packaging_spec_json, batch_output_basis, tolerance_pct,"
            " technical_parameters_json, quality_constraints_json, substitutions_json,"
            " effective_version, captured_by_user_id, captured_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snapshot.id, snapshot.operation_id, snapshot.processing_order_id,
             snapshot.process_type.value, snapshot.target_product_id,
             snapshot.recipe_version_id, snapshot.cutting_scheme_version_id,
             snapshot.yield_profile_version_id,
             json.dumps(snapshot.packaging_spec, sort_keys=True),
             str(snapshot.batch_output_basis), _txt(snapshot.tolerance_pct),
             json.dumps(snapshot.technical_parameters, sort_keys=True),
             json.dumps(snapshot.quality_constraints, sort_keys=True),
             json.dumps(list(snapshot.substitutions)), snapshot.effective_version,
             snapshot.captured_by_user_id, snapshot.captured_at.isoformat()))
        for entrada in snapshot.inputs:
            self._conn.execute(
                "INSERT INTO processing_recipe_snapshot_inputs (id, snapshot_id, product_id,"
                " role, quantity_per_basis, unit_id, scrap_pct, sequence, lot_controlled)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (new_uuid(), snapshot.id, entrada.product_id, entrada.role.value,
                 str(entrada.quantity_per_basis), entrada.unit_id, str(entrada.scrap_pct),
                 entrada.sequence, int(entrada.lot_controlled)))
        for salida in snapshot.outputs:
            self._conn.execute(
                "INSERT INTO processing_recipe_snapshot_outputs (id, snapshot_id, product_id,"
                " output_type, measure_kind, expected_factor, expected_yield_pct,"
                " minimum_yield_pct, maximum_yield_pct, unit_id, sequence, lot_controlled,"
                " quality_gate, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), snapshot.id, salida.product_id, salida.output_type.value,
                 salida.measure_kind, str(salida.expected_factor),
                 _txt(salida.expected_yield_pct), _txt(salida.minimum_yield_pct),
                 _txt(salida.maximum_yield_pct), salida.unit_id, salida.sequence,
                 int(salida.lot_controlled), int(salida.quality_gate), salida.source))

    def get_by_order(self, processing_order_id: str) -> ProcessingRecipeSnapshot | None:
        fila = self._conn.execute(
            "SELECT id, operation_id, processing_order_id, process_type, target_product_id,"
            " recipe_version_id, cutting_scheme_version_id, yield_profile_version_id,"
            " packaging_spec_json, batch_output_basis, tolerance_pct,"
            " technical_parameters_json, quality_constraints_json, substitutions_json,"
            " effective_version, captured_by_user_id, captured_at"
            " FROM processing_recipe_snapshots WHERE processing_order_id=?",
            (processing_order_id,)).fetchone()
        if fila is None:
            return None
        (sid, operation_id, order_id, process_type, target, recipe, scheme, yield_profile,
         packaging, basis, tolerance, technical, quality, substitutions, effective,
         captured_by, captured_at) = tuple(fila)
        entradas = tuple(
            SnapshotInput(product_id=r[0], role=InputRole(r[1]),
                          quantity_per_basis=Decimal(str(r[2])), unit_id=r[3],
                          scrap_pct=Decimal(str(r[4])), sequence=r[5],
                          lot_controlled=bool(r[6]))
            for r in self._conn.execute(
                "SELECT product_id, role, quantity_per_basis, unit_id, scrap_pct, sequence,"
                " lot_controlled FROM processing_recipe_snapshot_inputs WHERE snapshot_id=?"
                " ORDER BY sequence, product_id", (sid,)).fetchall())
        salidas = tuple(
            SnapshotOutput(product_id=r[0], output_type=r[1], measure_kind=r[2],
                           expected_factor=Decimal(str(r[3])), expected_yield_pct=_dec(r[4]),
                           minimum_yield_pct=_dec(r[5]), maximum_yield_pct=_dec(r[6]),
                           unit_id=r[7], sequence=r[8], lot_controlled=bool(r[9]),
                           quality_gate=bool(r[10]), source=r[11])
            for r in self._conn.execute(
                "SELECT product_id, output_type, measure_kind, expected_factor,"
                " expected_yield_pct, minimum_yield_pct, maximum_yield_pct, unit_id, sequence,"
                " lot_controlled, quality_gate, source FROM processing_recipe_snapshot_outputs"
                " WHERE snapshot_id=? ORDER BY sequence, product_id", (sid,)).fetchall())
        return ProcessingRecipeSnapshot(
            process_type=process_type, target_product_id=target, inputs=entradas,
            outputs=salidas, recipe_version_id=recipe, cutting_scheme_version_id=scheme,
            yield_profile_version_id=yield_profile, packaging_spec=json.loads(packaging or "{}"),
            batch_output_basis=Decimal(str(basis)), tolerance_pct=_dec(tolerance),
            technical_parameters=json.loads(technical or "{}"),
            quality_constraints=json.loads(quality or "{}"),
            substitutions=tuple(json.loads(substitutions or "[]")),
            effective_version=effective or "", id=sid, processing_order_id=order_id,
            operation_id=operation_id, captured_by_user_id=captured_by,
            captured_at=datetime.fromisoformat(captured_at))

"""Remediación D1 (paso 1) — Bloquea la ruta canónica de caja.

Contexto (DEEP_AUDIT_ALL_MODULES §8/§17, D1). La caja NO es "3 servicios en
paralelo" sino una arquitectura EN CAPAS cuya ruta de producción ya es canónica:

    UI (modulos/caja.py)
      → open_cash_shift_uc / register_cash_movement_uc / generate_z_cut_uc  (use cases)
      → CashRegisterApplicationService  (única emisora de eventos CASH_*)
      → finance_service.{abrir_turno, registrar_movimiento_manual, generar_corte_z}

`CajaApplicationService` se usa desde la UI SÓLO para lecturas (KPIs, historial,
arqueo, estado de turno); sus métodos de mutación son un duplicado histórico que
hoy no está en la ruta de producción. Estos tests IMPIDEN que la UI regrese a la
ruta legacy (llamar mutaciones de caja directamente sobre el servicio) y fijan que
las mutaciones sólo ocurran vía los use cases canónicos.

La unificación de las 3 implementaciones de corte Z (finance_service /
CajaApplicationService / CierreCajaService del scheduler) es trabajo posterior de
D1 con cobertura financiera dedicada; ver migrations/MIGRATION_LOG.md (D1).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CAJA_UI = REPO / "modulos" / "caja.py"

# Mutaciones de turno/caja que la UI NO debe invocar directamente sobre un
# servicio: deben pasar por los use cases canónicos.
CAJA_MUTATIONS = ("abrir_turno", "generar_corte_z", "registrar_movimiento_manual")

CANONICAL_USE_CASES = (
    "generate_z_cut_uc",
    "open_cash_shift_uc",
    "register_cash_movement_uc",
)


def _ui_source() -> str:
    return CAJA_UI.read_text(encoding="utf-8")


def test_caja_ui_does_not_call_shift_mutations_directly():
    """La UI de caja no invoca mutaciones de turno directamente (ruta legacy)."""
    src = _ui_source()
    offenders = [m for m in CAJA_MUTATIONS if re.search(rf"\.{m}\s*\(", src)]
    assert not offenders, (
        "modulos/caja.py invoca mutaciones de caja directamente sobre el servicio "
        f"(deben pasar por los use cases canónicos): {offenders}"
    )


def test_caja_ui_uses_canonical_use_cases():
    """Las mutaciones de caja de la UI se enrutan por los use cases canónicos."""
    src = _ui_source()
    missing = [uc for uc in CANONICAL_USE_CASES if uc not in src]
    assert not missing, (
        "modulos/caja.py debe enrutar por los use cases canónicos de caja; "
        f"faltan referencias a: {missing}"
    )


def test_cash_register_service_is_sole_cash_event_emitter():
    """CashRegisterApplicationService emite CASH_* y delega la lógica de turno."""
    svc = (REPO / "backend" / "application" / "services"
           / "cash_register_application_service.py").read_text(encoding="utf-8")
    for evt in ("CASH_SHIFT_OPENED", "CASH_MOVEMENT_RECORDED", "CASH_Z_CUT_GENERATED"):
        assert evt in svc, f"CashRegisterApplicationService debe emitir {evt}"
    # Delega la lógica de turno en finance_service (no reimplementa SQL de caja).
    for m in CAJA_MUTATIONS:
        assert f"_fin.{m}" in svc, (
            f"CashRegisterApplicationService debe delegar {m} en finance_service"
        )

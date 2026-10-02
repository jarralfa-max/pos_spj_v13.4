"""Ruta canónica ÚNICA de caja.

    UI (modulos/caja.py)
      → open_cash_shift_uc / register_cash_movement_uc / generate_z_cut_uc  (use cases)
      → CashRegisterApplicationService  (única emisora de eventos CASH_*)
      → CajaApplicationService.{abrir_turno, registrar_movimiento_manual,
                                generar_corte_z}  (única implementación)

La UI lee directo de CajaApplicationService (KPIs, historial, arqueo, estado de
turno) pero NO invoca sus mutaciones: deben pasar por los use cases. FinanceService
solo conserva delegados finos hacia la misma instancia.
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


def test_no_production_code_reads_turno_actual_table():
    """El tracker legacy `turno_actual` está retirado: todo el código de
    producción usa el modelo canónico `turnos_caja`. Sin excepciones."""
    prod_dirs = ("core", "modulos", "application", "backend", "interfaz", "ui")
    # Acceso SQL a la tabla (no el atributo self.turno_actual de la UI).
    sql_access = re.compile(r"(?i)\b(from|into|update|join)\s+turno_actual\b")
    allow: set[str] = set()

    offenders = []
    for rel_dir in prod_dirs:
        base = REPO / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if rel in allow:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if sql_access.search(text):
                offenders.append(rel)

    assert not offenders, (
        "Código de producción accede a la tabla legacy `turno_actual` "
        f"(usar `turnos_caja`): {sorted(set(offenders))}"
    )


def test_cash_register_service_is_sole_cash_event_emitter():
    """CashRegisterApplicationService emite CASH_* y delega la lógica de turno."""
    svc = (REPO / "backend" / "application" / "services"
           / "cash_register_application_service.py").read_text(encoding="utf-8")
    for evt in ("CASH_SHIFT_OPENED", "CASH_MOVEMENT_RECORDED", "CASH_Z_CUT_GENERATED"):
        assert evt in svc, f"CashRegisterApplicationService debe emitir {evt}"
    # Delega la lógica de turno en la implementación única (no reimplementa SQL).
    for m in CAJA_MUTATIONS:
        assert f"_caja.{m}" in svc, (
            f"CashRegisterApplicationService debe delegar {m} en CajaApplicationService"
        )
    assert "INSERT INTO" not in svc and "UPDATE turnos_caja" not in svc


def test_no_parallel_cash_vocabulary_or_ledger_in_production():
    """Un solo canal (CASH_*) y una sola implementación de turnos.

    Prohíbe el vocabulario CAJA_* (duplicaba cada evento vía bridge),
    CierreCajaService y CajaRepository (ledgers paralelos sin consumidores).
    """
    prod_dirs = ("core", "modulos", "application", "backend", "interfaz",
                 "ui", "repositories")
    legacy = re.compile(
        r"CAJA_(TURNO_ABIERTO|TURNO_CERRADO|MOVIMIENTO|CORTE_Z_GENERADO|"
        r"DIFERENCIA_DETECTADA)|cash_event_bridge|CierreCajaService|"
        r"from repositories\.caja import"
    )
    offenders = []
    for rel_dir in prod_dirs:
        base = REPO / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if legacy.search(text):
                offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, f"Rutas de caja legacy reintroducidas: {offenders}"

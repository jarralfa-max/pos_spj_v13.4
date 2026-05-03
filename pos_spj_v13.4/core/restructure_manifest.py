# core/restructure_manifest.py — SPJ POS v13.30 — FASE 12
"""
Manifiesto de reestructuración — documenta qué se reemplazó, qué quedó
deprecado y cuál es la nueva arquitectura canónica.

EJECUCIÓN:
    python core/restructure_manifest.py
    → Imprime reporte de estado: activos, deprecados, migrados

PROPÓSITO: Guía para limpieza futura sin romper producción hoy.
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
#  MAPA DE REEMPLAZO: viejo → nuevo
# ══════════════════════════════════════════════════════════════════════════════

REPLACEMENTS = {
    # ── IMPRESIÓN (Fase 1) ────────────────────────────────────────────────────
    "hardware_utils._imprimir_win32": {
        "replaced_by": "core.services.printer_service.PrintTransport._send_win32",
        "status": "deprecated",
        "lines": 471,
        "reason": "Duplicación de transporte de impresión",
    },
    "hardware_utils._imprimir_escpos": {
        "replaced_by": "core.services.printer_service.PrintTransport",
        "status": "deprecated",
        "lines": 471,
    },
    "hardware_utils._print_queue": {
        "replaced_by": "core.services.printer_service.PrintQueue",
        "status": "deprecated",
        "reason": "Cola sin prioridad ni reintentos",
    },
    "core.services.ticket_printer": {
        "replaced_by": "core.services.printer_service.PrinterService.print_ticket",
        "status": "deprecated",
        "lines": 65,
    },

    # ── FIDELIZACIÓN (Fase 2) ─────────────────────────────────────────────────
    "core.engines.loyalty_engine": {
        "replaced_by": "core.services.loyalty_service.LoyaltyService",
        "status": "dead_code",
        "lines": 62,
        "reason": "0 referencias — nunca se importa",
    },
    "core.services.fidelidad_engine": {
        "replaced_by": "core.services.loyalty_service.LoyaltyService",
        "status": "deprecated",
        "lines": 410,
        "reason": "Reemplazado por GrowthEngine wrapped en LoyaltyService",
    },
    "core.services.enterprise.loyalty_enterprise_engine": {
        "replaced_by": "core.services.loyalty_service.LoyaltyService",
        "status": "dead_code",
        "lines": 812,
        "reason": "0 referencias — nunca se importa",
    },
    "core.services.loyalty_admin_service": {
        "replaced_by": "core.services.loyalty_service.LoyaltyService",
        "status": "deprecated",
        "lines": 74,
    },

    # ── REPORTES (posible código muerto) ──────────────────────────────────────
    "core.services.enterprise.report_charts": {
        "replaced_by": "N/A",
        "status": "dead_code",
        "lines": 592,
        "reason": "0 referencias",
    },
    "core.services.enterprise.report_exporter": {
        "replaced_by": "N/A",
        "status": "dead_code",
        "lines": 458,
        "reason": "0 referencias",
    },
}

# ══════════════════════════════════════════════════════════════════════════════
#  ARQUITECTURA NUEVA (Fases 1-13)
# ══════════════════════════════════════════════════════════════════════════════

NEW_ARCHITECTURE = {
    "core/module_config.py":                "Fase 1:  Toggles globales de módulos",
    "core/services/printer_service.py":     "Fase 1:  PrinterService unificado",
    "core/ticket_escpos_renderer.py":       "Fase 1:  ESC/POS renderer con logo/QR",
    "core/services/loyalty_service.py":     "Fase 2:  LoyaltyService (wraps GrowthEngine)",
    "core/services/treasury_service.py":    "Fase 3:  Tesorería Central / CAPEX",
    "core/services/alert_engine.py":        "Fase 4:  Alertas inteligentes (6 categorías)",
    "core/services/decision_engine.py":     "Fase 5:  DecisionEngine (solo sugerencias)",
    "core/services/actionable_forecast.py": "Fase 6:  Forecast → acciones",
    "core/services/financial_simulator.py": "Fase 7:  Simulador financiero",
    "core/services/ai_advisor.py":          "Fase 8:  IA con DeepSeek (opcional)",
    "core/services/ceo_dashboard.py":       "Fase 9:  CEO Dashboard",
    "core/services/franchise_manager.py":   "Fase 10: Modo franquicia",
    "core/services/expansion_analyzer.py":  "Fase 11: IA expansión estratégica",
    "core/restructure_manifest.py":         "Fase 12: Manifiesto de reestructuración",
    "core/migration_validator.py":          "Fase 13: Validador de migración",
}

# ══════════════════════════════════════════════════════════════════════════════
#  ARCHIVOS SEGUROS DE ELIMINAR (0 referencias, código muerto confirmado)
# ══════════════════════════════════════════════════════════════════════════════

SAFE_TO_DELETE = []
# v13.30: TODOS los archivos muertos ya fueron eliminados:
# ✅ core/engines/loyalty_engine.py (62 ln)
# ✅ core/services/enterprise/loyalty_enterprise_engine.py (812 ln)
# ✅ core/services/enterprise/report_charts.py (592 ln)
# ✅ core/services/enterprise/report_exporter.py (458 ln)
# ✅ core/services/fidelidad_engine.py (410 ln)
# ✅ core/services/ticket_printer.py (112 ln)
# ✅ core/services/loyalty_admin_service.py (74 ln)
# ✅ hardware_utils.py (471 ln)
# ✅ core/services/product_recipe_repository.py (311 ln)
# ✅ core/services/ticket_layout_service.py (147 ln)
# ✅ core/services/batch_tree_audit_engine.py (48 ln)
# ✅ core/services/batch_tree_guard.py (70 ln)
# ✅ core/services/margin_audit_engine.py (87 ln)
# ✅ core/services/event_hashing.py (6 ln)
# ✅ core/services/inventory_manager.py (7 ln)
# ✅ core/services/sales_transaction_service.py (7 ln)
# ✅ core/services/devolucion_service.py (41 ln)
# ✅ core/services/promotion_service.py (69 ln)
# ✅ core/services/referidos_service.py (56 ln)
# ✅ core/services/paquete_service.py (267 ln)
# ✅ core/services/delivery_service.py (104 ln)
# ✅ scheduler_worker.py (196 ln)
#
# Total eliminado: 4,407 líneas de código muerto/duplicado

# ══════════════════════════════════════════════════════════════════════════════
#  ARCHIVOS DEPRECADOS (tienen refs pero deben migrar gradualmente)
# ══════════════════════════════════════════════════════════════════════════════

DEPRECATED_KEEP = []
# v13.30: TODOS los archivos deprecados fueron migrados y eliminados.
# ✅ hardware_utils.py → safe_serial_read extraído a hardware/scale_reader.py
#                       → impresión migrada a PrinterService
# ✅ fidelidad_engine.py → reemplazado por LoyaltyService
# ✅ loyalty_admin_service.py → absorbido por LoyaltyService
# ✅ ticket_printer.py → absorbido por PrinterService


# ══════════════════════════════════════════════════════════════════════════════
#  CLI — Ejecutar como script para ver estado
# ══════════════════════════════════════════════════════════════════════════════

def print_report():
    print("=" * 60)
    print("  SPJ POS v13.30 — REPORTE DE REESTRUCTURACIÓN (Fase 12)")
    print("=" * 60)

    print("\n📁 ARQUITECTURA NUEVA (14 servicios):")
    total_new = 0
    for f, desc in NEW_ARCHITECTURE.items():
        try:
            with open(f) as fh:
                ln = sum(1 for _ in fh)
            total_new += ln
            print(f"  ✅ {f:<48} {ln:>4} ln — {desc}")
        except FileNotFoundError:
            print(f"  ❌ {f:<48} FALTA — {desc}")
    print(f"  {'TOTAL':<48} {total_new:>4} líneas nuevas")

    print("\n🗑️  CÓDIGO MUERTO (seguro de eliminar):")
    total_dead = 0
    for f in SAFE_TO_DELETE:
        try:
            with open(f) as fh:
                ln = sum(1 for _ in fh)
            total_dead += ln
            print(f"  🔴 {f:<48} {ln:>4} ln — 0 referencias")
        except FileNotFoundError:
            print(f"  ✅ {f:<48} YA ELIMINADO")
    print(f"  {'TOTAL RECUPERABLE':<48} {total_dead:>4} líneas")

    print("\n⚠️  DEPRECADO (migrar antes de eliminar):")
    total_dep = 0
    for d in DEPRECATED_KEEP:
        total_dep += d["lines"]
        print(f"  🟡 {d['file']:<48} {d['lines']:>4} ln")
        print(f"       Blocker: {d['blocker']}")
        print(f"       Migrar:  {d['migration']}")
    print(f"  {'TOTAL DEPRECADO':<48} {total_dep:>4} líneas")

    print(f"\n📊 RESUMEN:")
    print(f"   Código nuevo (Fases 1-13):     {total_new:>5} líneas")
    print(f"   Código muerto (eliminar):      {total_dead:>5} líneas")
    print(f"   Código deprecado (migrar):     {total_dep:>5} líneas")
    print(f"   Reducción potencial:           {total_dead + total_dep:>5} líneas")
    print()


if __name__ == "__main__":
    print_report()

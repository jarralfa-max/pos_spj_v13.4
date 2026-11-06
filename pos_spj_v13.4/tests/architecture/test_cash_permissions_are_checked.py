"""SDLC-ARQ-SHIFT-003: un permiso de Caja que nadie comprueba promete algo que
no existe. Toda acción del catálogo se comprueba en el backend, salvo las de
`SIN_COMPROBAR`: la deuda medida el 2026-11-05, que sólo puede encogerse."""
from pathlib import Path
import re

from backend.application.cash_register.permissions import CashPermissions

ROOT = Path(__file__).resolve().parents[2]

SIN_COMPROBAR = frozenset({
    "REGISTER_VIEW", "REGISTER_CREATE", "REGISTER_EDIT", "DRAWER_VIEW", "TERMINAL_VIEW",
    "BLIND_COUNT_CANCEL", "DIFFERENCE_WRITE_OFF", "SAFE_DROP_VIEW", "SAFE_DROP_CREATE",
    "SAFE_DROP_AUTHORIZE", "HANDOVER_CANCEL", "DEPOSIT_PREPARE", "DEPOSIT_CANCEL",
    "PAYMENT_VIEW", "PAYMENT_REGISTER", "PAYMENT_REVERSE", "PAYMENT_METHOD_MANAGE",
    "PAYMENT_TERMINAL_MANAGE", "PAYMENT_TERMINAL_RECONCILE_OPERATION", "REFUND_EXECUTE",
    "REFUND_OVERRIDE", "HARDWARE_VIEW", "HARDWARE_MANAGE", "SETTINGS_VIEW",
    "WHATSAPP_MANAGE",
})


def _backend_text() -> str:
    parts = []
    for base in ("backend/application", "backend/infrastructure"):
        for path in (ROOT / base).rglob("*.py"):
            if path.name != "permissions.py":
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def _unchecked() -> set[str]:
    text = _backend_text()
    names = {name: value for name, value in vars(CashPermissions).items()
             if name.isupper()}
    return {name for name, code in names.items()
            if not re.search(r"\b(?:CashPermissions|P)\." + name + r"\b", text)
            and code not in text}


def test_ningun_permiso_nuevo_queda_sin_comprobar():
    assert _unchecked() <= SIN_COMPROBAR


def test_la_lista_de_deuda_no_guarda_permisos_ya_comprobados():
    assert SIN_COMPROBAR <= _unchecked()


def test_cerrar_turno_y_revisar_z_ya_se_comprueban():
    assert not {"SHIFT_CLOSE", "Z_CUT_REVIEW", "SHIFT_INTERVENE",
                "MOVEMENT_INTERVENE"} & _unchecked()

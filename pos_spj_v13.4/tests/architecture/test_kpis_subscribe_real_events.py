"""Remediación E (T9) — Todo evento suscrito por la UI tiene un emisor real.

Contrato: los KPIs/dashboards se refrescan por EVENTOS, no por timers. Este
guardrail hace AST sobre las capas de presentación (modulos/, ui/, interfaz/) y
verifica que cada canal que un módulo `subscribe(...)` sea publicado por algún
`publish(...)` en el código (o esté en la allowlist de canales inter-proceso).

Resuelve los eventos referenciados como literal, como constante de
core.events.event_bus / core.events.domain_events, como `EventName.X.value`, y
el patrón `for evt in (…): bus.subscribe(evt, …)`.

Bloquea B6/B10 (suscripciones a canales sin emisor) y su regreso.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_DIRS = ("modulos", "ui", "interfaz")
# Directorios donde puede vivir un emisor (publish).
PUB_DIRS = ("modulos", "ui", "interfaz", "core", "application", "backend",
            "repositories", "services", "integrations", "sync", "notifications")

# Canales con emisor REAL pero no resoluble por AST (emisión dinámica). Se emiten
# vía dict-dispatch en core/events/catalog_events.py:
#   bus.publish(_PRODUCT_EVENT_BY_ACTION[action], ...) con valores PRODUCTO_CREADO/
#   PRODUCTO_ACTUALIZADO/PRODUCTO_ELIMINADO.
EXTERNAL_ALLOWLIST: set[str] = {
    "PRODUCTO_CREADO", "PRODUCTO_ACTUALIZADO", "PRODUCTO_ELIMINADO",
}


def _name_value_map() -> dict:
    vals: dict[str, str] = {}
    try:
        import core.events.event_bus as eb
        import core.events.domain_events as de
        for mod in (eb, de):
            for k in dir(mod):
                if k.isupper() and isinstance(getattr(mod, k), str):
                    vals[k] = getattr(mod, k)
    except Exception:
        pass
    try:
        from backend.shared.events.event_names import EventName
        for m in EventName:
            vals[f"EventName.{m.name}"] = m.value
    except Exception:
        pass
    return vals


NAME2VAL = _name_value_map()


def _elt_value(node):
    """Resuelve un nodo AST a un valor de evento (str) o None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return NAME2VAL.get(node.id)
    if isinstance(node, ast.Attribute):
        # EventName.X.value
        if (node.attr == "value" and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "EventName"):
            return NAME2VAL.get(f"EventName.{node.value.attr}")
        # modulo.CONST
        return NAME2VAL.get(node.attr)
    return None


def _calls_named(tree, name):
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and n.args):
            continue
        fn = n.func
        fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if fname == name:
            yield n


def _subscribed_values(tree) -> set:
    vals: set = set()
    # Suscripciones directas.
    for call in _calls_named(tree, "subscribe"):
        v = _elt_value(call.args[0])
        if v:
            vals.add(v)
    # Patrón for evt in (…): subscribe(evt, …)
    for n in ast.walk(tree):
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) \
                and isinstance(n.iter, (ast.Tuple, ast.List)):
            tvar = n.target.id
            uses_target = any(
                isinstance(c.args[0], ast.Name) and c.args[0].id == tvar
                for c in _calls_named(n, "subscribe")
            )
            if uses_target:
                for elt in n.iter.elts:
                    v = _elt_value(elt)
                    if v:
                        vals.add(v)
    return vals


# Métodos que emiten un evento (además de bus.publish): wrappers y helpers.
_PUBLISH_METHODS = ("publish", "_publish", "_publish_safe", "publish_event", "emit")


def _publish_calls(tree):
    for name in _PUBLISH_METHODS:
        yield from _calls_named(tree, name)


def _published_values(tree) -> set:
    vals: set = set()
    for call in _publish_calls(tree):
        v = _elt_value(call.args[0])
        if v:
            vals.add(v)
    # for evt in (…): publish(evt, …)
    for n in ast.walk(tree):
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) \
                and isinstance(n.iter, (ast.Tuple, ast.List)):
            tvar = n.target.id
            if any(isinstance(c.args[0], ast.Name) and c.args[0].id == tvar
                   for c in _publish_calls(n)):
                for elt in n.iter.elts:
                    v = _elt_value(elt)
                    if v:
                        vals.add(v)
    return vals


def _iter_py(dirs):
    for d in dirs:
        base = REPO / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                yield path, ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue


def test_ui_subscriptions_have_emitters():
    ui_subs: dict[str, set] = {}
    for path, tree in _iter_py(UI_DIRS):
        subs = _subscribed_values(tree)
        if subs:
            ui_subs[path.relative_to(REPO).as_posix()] = subs

    published: set = set()
    for _path, tree in _iter_py(PUB_DIRS):
        published |= _published_values(tree)

    offenders: dict[str, set] = {}
    for rel, subs in ui_subs.items():
        orphan = subs - published - EXTERNAL_ALLOWLIST
        if orphan:
            offenders[rel] = orphan

    assert not offenders, (
        "Módulos UI suscritos a canales SIN emisor (KPIs no event-driven / B6/B10):\n  "
        + "\n  ".join(f"{k}: {sorted(v)}" for k, v in sorted(offenders.items()))
    )

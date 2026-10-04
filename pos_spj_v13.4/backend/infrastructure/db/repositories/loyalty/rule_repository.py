"""Persistencia de reglas de acumulación (§13), combinación de beneficios (§24)
y lo que el motor necesita leer para evaluar una compra (2026-10-03).

Las lecturas de otros contextos (categoría del producto, segmentos del
cliente) son de SOLO LECTURA y sólo de identificadores: Fidelidad no copia
catálogo ni identidad. Una tabla ausente se lee como vacía.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from backend.domain.loyalty.entities.loyalty_rule import LoyaltyRule
from backend.domain.loyalty.enums import LoyaltyRuleStatus, LoyaltyRuleType, StackingCombination, StackingOption
from backend.domain.loyalty.policies.stacking_policy import StackingSetting
from backend.domain.loyalty.services.rule_engine import RuleUsage
from backend.infrastructure.db.repositories.loyalty.base import now_iso
from backend.shared.ids import new_uuid

_SCOPES = ("branch_scope", "channel_scope", "payment_method_scope", "product_scope",
           "category_scope", "customer_segment_scope")
_COLUMNS = ("id", "code", "name", "rule_type", "status", "priority", "program_id",
            "condition_definition", "benefit_definition", "effective_from", "effective_to",
            "stackable", "maximum_uses", "customer_limit", "daily_limit", "monthly_limit",
            *_SCOPES, "created_by_user_id", "activated_by_user_id", "activated_at",
            "deactivated_at", "created_at", "updated_at")


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    try:
        cursor = conn.execute(sql, params)
    except sqlite3.OperationalError:
        return []
    nombres = [d[0] for d in cursor.description]
    return [dict(zip(nombres, fila)) for fila in cursor.fetchall()]


def _to_rule(row: dict) -> LoyaltyRule:
    datos = dict(row)
    return LoyaltyRule(
        id=datos["id"], code=datos["code"], name=datos["name"],
        rule_type=LoyaltyRuleType(datos["rule_type"]),
        created_by_user_id=datos["created_by_user_id"], priority=int(datos["priority"]),
        program_id=datos["program_id"],
        condition_definition=json.loads(datos["condition_definition"] or "{}"),
        benefit_definition=json.loads(datos["benefit_definition"] or "{}"),
        effective_from=datos["effective_from"], effective_to=datos["effective_to"],
        stackable=bool(datos["stackable"]), maximum_uses=datos["maximum_uses"],
        customer_limit=datos["customer_limit"], daily_limit=datos["daily_limit"],
        monthly_limit=datos["monthly_limit"],
        **{s: tuple(json.loads(datos[s] or "[]")) for s in _SCOPES},
        status=LoyaltyRuleStatus(datos["status"]),
        activated_by_user_id=datos["activated_by_user_id"], activated_at=datos["activated_at"],
        deactivated_at=datos["deactivated_at"], created_at=datos["created_at"],
        updated_at=datos["updated_at"])


class LoyaltyRuleRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── reglas ────────────────────────────────────────────────────────────
    def save(self, rule: LoyaltyRule) -> None:
        valores = {
            "id": rule.id, "code": rule.code, "name": rule.name,
            "rule_type": rule.rule_type.value, "status": rule.status.value,
            "priority": rule.priority, "program_id": rule.program_id,
            "condition_definition": json.dumps(rule.condition_definition, ensure_ascii=False),
            "benefit_definition": json.dumps(rule.benefit_definition, ensure_ascii=False),
            "effective_from": rule.effective_from, "effective_to": rule.effective_to,
            "stackable": 1 if rule.stackable else 0, "maximum_uses": rule.maximum_uses,
            "customer_limit": rule.customer_limit, "daily_limit": rule.daily_limit,
            "monthly_limit": rule.monthly_limit,
            **{s: json.dumps(list(getattr(rule, s)), ensure_ascii=False) for s in _SCOPES},
            "created_by_user_id": rule.created_by_user_id,
            "activated_by_user_id": rule.activated_by_user_id, "activated_at": rule.activated_at,
            "deactivated_at": rule.deactivated_at, "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }
        columnas = ", ".join(_COLUMNS)
        marcas = ", ".join("?" for _ in _COLUMNS)
        cambios = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS if c not in ("id", "created_at"))
        self._conn.execute(
            f"INSERT INTO loyalty_rules ({columnas}) VALUES ({marcas})"
            f" ON CONFLICT(id) DO UPDATE SET {cambios}",
            tuple(valores[c] for c in _COLUMNS))

    def get(self, rule_id: str) -> LoyaltyRule | None:
        filas = _rows(self._conn, f"SELECT {', '.join(_COLUMNS)} FROM loyalty_rules WHERE id=?",
                      (rule_id,))
        return _to_rule(filas[0]) if filas else None

    def get_by_code(self, code: str) -> LoyaltyRule | None:
        filas = _rows(self._conn, f"SELECT {', '.join(_COLUMNS)} FROM loyalty_rules WHERE code=?",
                      (str(code or "").strip().upper(),))
        return _to_rule(filas[0]) if filas else None

    def list_active(self) -> list[LoyaltyRule]:
        return [_to_rule(f) for f in _rows(
            self._conn, f"SELECT {', '.join(_COLUMNS)} FROM loyalty_rules WHERE status='ACTIVE'")]

    # ── uso y evaluaciones ────────────────────────────────────────────────
    def usage(self, rule_ids: list[str], customer_id: str | None,
              moment: datetime) -> dict[str, RuleUsage]:
        if not rule_ids:
            return {}
        dia = moment.date().isoformat()
        mes = dia[:7]
        marcas = ",".join("?" for _ in rule_ids)
        filas = _rows(
            self._conn,
            "SELECT rule_id, COUNT(*) AS total,"
            " SUM(CASE WHEN customer_id = ? THEN 1 ELSE 0 END) AS cliente,"
            " SUM(CASE WHEN customer_id = ? AND substr(applied_at, 1, 10) = ? THEN 1 ELSE 0 END) AS hoy,"
            " SUM(CASE WHEN customer_id = ? AND substr(applied_at, 1, 7) = ? THEN 1 ELSE 0 END) AS mes"
            f" FROM loyalty_rule_applications WHERE rule_id IN ({marcas}) GROUP BY rule_id",
            (customer_id or "", customer_id or "", dia, customer_id or "", mes, *rule_ids))
        return {f["rule_id"]: RuleUsage(total=int(f["total"] or 0), customer=int(f["cliente"] or 0),
                                         customer_today=int(f["hoy"] or 0),
                                         customer_month=int(f["mes"] or 0)) for f in filas}

    def evaluation_for(self, sale_id: str) -> dict | None:
        filas = _rows(self._conn, "SELECT * FROM loyalty_sale_evaluations WHERE sale_id=?",
                      (sale_id,))
        return filas[0] if filas else None

    def previous_purchases(self, customer_id: str, until_iso: str,
                           exclude_sale_id: str | None = None) -> list[str]:
        """Compras evaluadas del cliente hasta `until_iso` (inclusive: dos ventas
        del mismo segundo son dos visitas), sin la venta que se evalúa."""
        return [f["evaluated_at"] for f in _rows(
            self._conn, "SELECT evaluated_at FROM loyalty_sale_evaluations"
            " WHERE customer_id=? AND evaluated_at <= ? AND sale_id <> ? ORDER BY evaluated_at",
            (customer_id, until_iso, exclude_sale_id or ""))]

    def _has(self, table: str) -> bool:
        """Una base sin la migración 295 evalúa con la base de la Configuración
        y no tiene dónde guardar el desglose: se omite, no revienta el cobro."""
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    def record_evaluation(self, *, sale_id: str, customer_id: str, loyalty_account_id: str | None,
                          points: int, breakdown: list[dict], evaluated_at: str) -> None:
        if not self._has("loyalty_sale_evaluations"):
            return
        self._conn.execute(
            "INSERT OR IGNORE INTO loyalty_sale_evaluations (sale_id, customer_id,"
            " loyalty_account_id, points, breakdown_json, evaluated_at) VALUES (?,?,?,?,?,?)",
            (sale_id, customer_id, loyalty_account_id, str(points),
             json.dumps(breakdown, ensure_ascii=False), evaluated_at))

    def record_application(self, *, rule_id: str, sale_id: str, customer_id: str | None,
                           points: int, applied_at: str) -> None:
        if not self._has("loyalty_rule_applications"):
            return
        self._conn.execute(
            "INSERT OR IGNORE INTO loyalty_rule_applications (id, rule_id, sale_id, customer_id,"
            " points, applied_at) VALUES (?,?,?,?,?,?)",
            (new_uuid(), rule_id, sale_id, customer_id, str(points), applied_at))

    # ── combinación de beneficios ─────────────────────────────────────────
    def stacking_settings(self) -> list[StackingSetting]:
        ajustes = []
        for f in _rows(self._conn, "SELECT * FROM loyalty_stacking_rules"):
            try:
                ajustes.append(StackingSetting(
                    combination=StackingCombination(f["combination"]),
                    option=StackingOption(f["option"]),
                    limit_value=Decimal(f["limit_value"]) if f["limit_value"] else None,
                    priority_order=tuple(json.loads(f["priority_order"] or "[]"))))
            except ValueError:
                continue
        return ajustes

    def save_stacking(self, setting: StackingSetting, *, actor_user_id: str) -> None:
        self._conn.execute(
            "INSERT INTO loyalty_stacking_rules (combination, option, limit_value,"
            " priority_order, updated_by_user_id, updated_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(combination) DO UPDATE SET option=excluded.option,"
            " limit_value=excluded.limit_value, priority_order=excluded.priority_order,"
            " updated_by_user_id=excluded.updated_by_user_id, updated_at=excluded.updated_at",
            (setting.combination.value, setting.option.value,
             str(setting.limit_value) if setting.limit_value is not None else None,
             json.dumps(list(setting.priority_order)), actor_user_id, now_iso()))


class LoyaltyAccrualContextReader:
    """Lo que el motor necesita de otros contextos, sólo identificadores."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def category_ids(self, product_ids: list[str]) -> dict[str, frozenset[str]]:
        if not product_ids:
            return {}
        marcas = ",".join("?" for _ in product_ids)
        directa = {f["id"]: f["category_id"] for f in _rows(
            self._conn, f"SELECT id, category_id FROM products WHERE id IN ({marcas})",
            tuple(product_ids))}
        padres = {f["id"]: f["parent_id"] for f in _rows(
            self._conn, "SELECT id, parent_id FROM product_categories")}
        resultado = {}
        for producto, categoria in directa.items():
            cadena, actual = set(), categoria
            while actual and actual not in cadena and len(cadena) < 20:
                cadena.add(actual)
                actual = padres.get(actual)
            resultado[producto] = frozenset(cadena)
        return resultado

    def segment_ids(self, customer_id: str | None) -> frozenset[str]:
        if not customer_id:
            return frozenset()
        return frozenset(f["segment_id"] for f in _rows(
            self._conn, "SELECT segment_id FROM customer_segment_memberships"
            " WHERE customer_id=? AND removed_at IS NULL", (customer_id,)))

    def program_ids(self, customer_id: str | None) -> frozenset[str]:
        if not customer_id:
            return frozenset()
        return frozenset(f["program_id"] for f in _rows(
            self._conn, "SELECT m.program_id FROM loyalty_memberships m"
            " JOIN loyalty_accounts a ON a.id = m.loyalty_account_id"
            " WHERE a.customer_id=? AND m.status='ACTIVE'", (customer_id,)))


class LoyaltyRuleScopeResolver:
    """Traduce lo que una persona escribe (códigos de producto y categoría,
    nombres de sucursal, códigos de segmento) a los identificadores que guarda
    la regla. Devuelve (ids, no_encontrados)."""

    _FUENTES = {
        "product": ("products", "code", "id"),
        "category": ("product_categories", "code", "id"),
        "branch": ("sucursales", "nombre", "id"),
        "segment": ("customer_segments", "code", "id"),
    }

    def __init__(self, connection) -> None:
        self._conn = connection

    def resolve(self, kind: str, values: list[str]) -> tuple[list[str], list[str]]:
        tabla, columna, ident = self._FUENTES[kind]
        ids: list[str] = []
        faltan: list[str] = []
        for valor in values:
            filas = _rows(self._conn, f"SELECT {ident} AS id FROM {tabla}"
                          f" WHERE UPPER({columna}) = UPPER(?) OR {ident} = ?", (valor, valor))
            if filas:
                ids.append(str(filas[0]["id"]))
            else:
                faltan.append(valor)
        return ids, faltan


__all__ = ["LoyaltyAccrualContextReader", "LoyaltyRuleRepository", "LoyaltyRuleScopeResolver"]

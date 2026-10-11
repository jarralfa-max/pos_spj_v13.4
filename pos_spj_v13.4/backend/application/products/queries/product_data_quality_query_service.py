"""ProductDataQualityQueryService (PROD-22, §35/§42) — calidad de datos del maestro.

Lista, por producto, qué le falta para estar completo y un puntaje 0-100. Las
reglas NO se reescriben aquí: son las de `detect_product_alerts` /
`detect_discontinued_still_active` (§35, las mismas que disparan las alertas),
más dos revisiones de completitud que no son alertas:

* cárnico con especie pero sin clasificación (categoría/corte, §11);
* vendible y activo sin imagen principal (la tarjeta del POS muestra iniciales).

Read-only; carga en bloque los indicadores de presencia (una consulta por tabla).
"""

from __future__ import annotations

from backend.application.products.notification_handlers.product_alert_detectors import (
    detect_discontinued_still_active,
    detect_product_alerts,
)
from backend.application.products.notifications.notification_policy import severity_for

ISSUE_ES = {
    "PRODUCT_INCOMPLETE": "Datos maestros incompletos (categoría, unidad o especie)",
    "MEAT_WITHOUT_SPECIES": "Producto cárnico sin especie",
    "PERISHABLE_WITHOUT_SHELF_LIFE": "Controla caducidad y no tiene vida útil",
    "CATCH_WEIGHT_WITHOUT_RANGE": "Peso variable sin rango configurado",
    "LOT_REQUIRED_NOT_CONFIGURED": "Requiere lote y no está configurado",
    "MEAT_WITHOUT_QUALITY_PROFILE": "Cárnico con control de calidad sin perfil de calidad",
    "PENDING_APPROVAL": "Pendiente de revisión",
    "DISCONTINUED_STILL_ACTIVE": "Descontinuado pero habilitado en sucursales",
    "MEAT_WITHOUT_CLASSIFICATION": "Cárnico sin categoría ni corte",
    "SELLABLE_WITHOUT_IMAGE": "Se vende y no tiene imagen para el POS",
}
_EXTRA_SEVERITY = {"MEAT_WITHOUT_CLASSIFICATION": "WARNING", "SELLABLE_WITHOUT_IMAGE": "INFO"}
#: Revisiones que se cuentan para el puntaje (las de proceso, como «pendiente de
#: revisión», informan pero no restan calidad).
_SCORED = tuple(k for k in ISSUE_ES if k != "PENDING_APPROVAL")


def _ids(conn, sql: str) -> set[str]:
    try:
        return {r[0] for r in conn.execute(sql).fetchall()}
    except Exception:  # tabla ausente en bases reducidas: nada presente
        return set()


class ProductDataQualityQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _presence(self) -> dict[str, set[str] | dict[str, int]]:
        c = self._conn
        branches: dict[str, int] = {}
        try:
            for pid, n in c.execute("SELECT product_id, COUNT(*) FROM branch_product "
                                    "WHERE enabled=1 GROUP BY product_id").fetchall():
                branches[pid] = int(n)
        except Exception:
            pass
        return {
            "shelf_life": _ids(c, "SELECT DISTINCT product_id FROM product_shelf_life_profiles"),
            "quality": _ids(c, "SELECT product_id FROM product_quality_profiles"),
            # «configurado» = activo y con rango; antes bastaba con que existiera la fila.
            "catch_weight": _ids(c, "SELECT product_id FROM product_catch_weight_config "
                                    "WHERE enabled=1 AND COALESCE(minimum_weight,'')<>'' "
                                    "AND COALESCE(maximum_weight,'')<>''"),
            "classified": _ids(c, "SELECT product_id FROM product_meat_classifications "
                                  "WHERE meat_category IS NOT NULL "
                                  "OR cut_classification_id IS NOT NULL"),
            "image": _ids(c, "SELECT product_id FROM product_images WHERE is_primary=1"),
            "branches": branches,
        }

    def report(self, *, only_with_issues: bool = True) -> list[dict]:
        from backend.application.products.use_cases.product_lifecycle_use_cases import (
            product_from_row,
        )
        presence = self._presence()
        cursor = self._conn.execute(
            "SELECT * FROM products WHERE lifecycle_status <> 'ARCHIVED' ORDER BY name")
        columns = [d[0] for d in cursor.description]
        rows: list[dict] = []
        for raw in cursor.fetchall():
            row = dict(zip(columns, raw))
            try:
                product = product_from_row(row)
            except Exception:  # fila con un tipo/estado que el dominio ya no acepta
                rows.append(self._entry(row, ["PRODUCT_INCOMPLETE"]))
                continue
            issues = [a.value for a in detect_product_alerts(
                product,
                has_shelf_life_profile=product.id in presence["shelf_life"],
                has_quality_profile=product.id in presence["quality"],
                catch_weight_configured=product.id in presence["catch_weight"])]
            discontinued = detect_discontinued_still_active(
                product, enabled_branch_count=presence["branches"].get(product.id, 0))
            if discontinued is not None:
                issues.append(discontinued.value)
            if product.is_meat and product.species_id and product.id not in presence["classified"]:
                issues.append("MEAT_WITHOUT_CLASSIFICATION")
            if (product.sellable and not product.is_internal
                    and row.get("lifecycle_status") == "ACTIVE"
                    and product.id not in presence["image"]):
                issues.append("SELLABLE_WITHOUT_IMAGE")
            entry = self._entry(row, issues)
            if issues or not only_with_issues:
                rows.append(entry)
        rows.sort(key=lambda r: (r["score"], r["name"] or ""))
        return rows

    @staticmethod
    def _entry(row: dict, issues: list[str]) -> dict:
        scored = sum(1 for i in issues if i in _SCORED)
        score = max(0, 100 - scored * 20)
        severities = [(_EXTRA_SEVERITY.get(i) or severity_for_value(i)) for i in issues]
        return {"product_id": row["id"], "code": row.get("code"), "name": row.get("name"),
                "product_type": row.get("product_type"),
                "lifecycle_status": row.get("lifecycle_status"),
                "issues": issues, "issue_labels": [ISSUE_ES.get(i, i) for i in issues],
                "severities": severities, "score": score}

    def summary(self) -> dict:
        report = self.report(only_with_issues=False)
        total = len(report)
        counts: dict[str, int] = {}
        for entry in report:
            for issue in entry["issues"]:
                counts[issue] = counts.get(issue, 0) + 1
        average = round(sum(e["score"] for e in report) / total) if total else 100
        return {"products": total,
                "with_issues": sum(1 for e in report if e["issues"]),
                "average_score": average, "by_issue": counts}


def severity_for_value(issue: str) -> str:
    from backend.domain.products.notification_enums import ProductAlertType
    try:
        return severity_for(ProductAlertType(issue)).value
    except ValueError:
        return "INFO"

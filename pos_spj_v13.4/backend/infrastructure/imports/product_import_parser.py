"""Parser de archivos de importación de productos (CSV / XLSX).

Lee un CSV (stdlib ``csv``) o un XLSX (stdlib ``zipfile`` + ``xml.etree`` — sin
dependencias externas) y devuelve filas como dicts con **claves canónicas** del
maestro (``code``, ``name``, ``product_type``, ``base_unit_id``, …). Los encabezados
en español o inglés se normalizan vía ``_HEADER_MAP``; las columnas desconocidas se
ignoran. No valida negocio (eso es del dominio) — sólo estructura el archivo.
"""

from __future__ import annotations

import csv
import io
import zipfile
from xml.etree import ElementTree as ET

#: Encabezado (normalizado) → campo canónico del maestro.
_HEADER_MAP = {
    "code": "code", "codigo": "code", "código": "code", "sku": "code",
    "name": "name", "nombre": "name", "descripcion corta": "short_name",
    "short_name": "short_name", "nombre corto": "short_name",
    "description": "description", "descripcion": "description",
    "descripción": "description",
    "product_type": "product_type", "tipo": "product_type",
    "tipo de producto": "product_type",
    "base_unit_id": "base_unit_id", "unidad": "base_unit_id",
    "unidad base": "base_unit_id", "unit": "base_unit_id",
    "category_id": "category_id", "categoria": "category_id",
    "categoría": "category_id", "brand_id": "brand_id", "marca": "brand_id",
}

CANONICAL_FIELDS = ("code", "name", "short_name", "description", "product_type",
                    "base_unit_id", "category_id", "brand_id")


def _norm_header(h: str) -> str:
    key = " ".join(str(h or "").strip().lower().split())
    return _HEADER_MAP.get(key, "")


def _rows_from_matrix(matrix: list[list[str]]) -> list[dict]:
    if not matrix:
        return []
    headers = [_norm_header(h) for h in matrix[0]]
    rows: list[dict] = []
    for raw in matrix[1:]:
        if not any((c or "").strip() for c in raw):
            continue  # salta filas vacías
        row = {}
        for idx, field in enumerate(headers):
            if not field:
                continue
            value = (raw[idx].strip() if idx < len(raw) and raw[idx] is not None
                     else "")
            row[field] = value
        rows.append(row)
    return rows


def parse_csv(text: str) -> list[dict]:
    reader = csv.reader(io.StringIO(text))
    return _rows_from_matrix([list(r) for r in reader])


# ── XLSX mínimo (sin openpyxl) ───────────────────────────────────────────────
def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _col_index(cell_ref: str) -> int:
    """'B3' → 1 (índice de columna base 0)."""
    letters = "".join(c for c in cell_ref if c.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def parse_xlsx(data: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root:
                text = "".join(t.text or "" for t in si.iter()
                               if _strip_ns(t.tag) == "t")
                shared.append(text)
        sheet_name = next((n for n in zf.namelist()
                           if n.startswith("xl/worksheets/sheet")), None)
        if sheet_name is None:
            return []
        root = ET.fromstring(zf.read(sheet_name))
        matrix: list[list[str]] = []
        for row_el in root.iter():
            if _strip_ns(row_el.tag) != "row":
                continue
            cells: dict[int, str] = {}
            for c in row_el:
                if _strip_ns(c.tag) != "c":
                    continue
                ref = c.attrib.get("r", "")
                col = _col_index(ref) if ref else len(cells)
                ctype = c.attrib.get("t", "")
                value = ""
                for child in c:
                    tag = _strip_ns(child.tag)
                    if tag == "v":
                        value = child.text or ""
                    elif tag == "is":  # inline string
                        value = "".join(t.text or "" for t in child.iter()
                                        if _strip_ns(t.tag) == "t")
                if ctype == "s" and value.isdigit():
                    value = shared[int(value)] if int(value) < len(shared) else ""
                cells[col] = value
            width = (max(cells) + 1) if cells else 0
            matrix.append([cells.get(i, "") for i in range(width)])
        return _rows_from_matrix(matrix)


def parse(filename: str, data: bytes) -> list[dict]:
    """Despacha por extensión. CSV se decodifica como UTF-8 (con BOM tolerado)."""
    lower = (filename or "").lower()
    if lower.endswith(".xlsx"):
        return parse_xlsx(data)
    return parse_csv(data.decode("utf-8-sig"))

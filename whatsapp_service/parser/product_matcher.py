# parser/product_matcher.py — Fuzzy match contra catálogo del ERP
"""
Busca productos por nombre aproximado usando Levenshtein distance.
No requiere ML — pura comparación de strings.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional, Tuple
from config.settings import FUZZY_MATCH_THRESHOLD

logger = logging.getLogger("wa.matcher")


def _levenshtein(s1: str, s2: str) -> int:
    """Distancia de Levenshtein sin dependencias externas."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


class ProductMatcher:
    """Busca productos en el catálogo del ERP por nombre aproximado."""

    def __init__(self, db_conn, sucursal_id: int = 1):
        self.db = db_conn
        self.sucursal_id = sucursal_id
        self._cache: List[Dict] = []
        self._categories: List[str] = []
        self.reload()

    def reload(self):
        """Recarga el catálogo de productos activos."""
        try:
            rows = self.db.execute("""
                SELECT p.id, p.nombre, p.precio,
                       COALESCE(bi.quantity, p.existencia, 0) as stock,
                       COALESCE(p.unidad, 'kg') as unidad,
                       COALESCE(p.categoria, '') as categoria
                FROM productos p
                LEFT JOIN branch_inventory bi
                    ON bi.product_id = p.id AND bi.branch_id = ?
                WHERE p.activo = 1 AND COALESCE(p.oculto, 0) = 0
                ORDER BY p.nombre
            """, (self.sucursal_id,)).fetchall()

            self._cache = [
                {
                    "id": r[0], "nombre": r[1], "precio": float(r[2] or 0),
                    "stock": float(r[3] or 0), "unidad": r[4],
                    "categoria": r[5],
                    "_nombre_lower": r[1].lower(),
                }
                for r in rows
            ]

            self._categories = sorted(set(
                p["categoria"] for p in self._cache if p["categoria"]
            ))
            logger.info("Catálogo cargado: %d productos, %d categorías",
                        len(self._cache), len(self._categories))
        except Exception as e:
            logger.error("Error cargando catálogo: %s", e)

    def set_sucursal(self, sucursal_id: int):
        if sucursal_id != self.sucursal_id:
            self.sucursal_id = sucursal_id
            self.reload()

    def get_categories(self) -> List[str]:
        return self._categories

    def get_by_category(self, category: str) -> List[Dict]:
        cat_lower = category.lower()
        return [p for p in self._cache if p["categoria"].lower() == cat_lower]

    def get_by_id(self, product_id: int) -> Optional[Dict]:
        for p in self._cache:
            if p["id"] == product_id:
                return p
        return None

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Búsqueda por nombre — exacta primero, luego fuzzy."""
        q = query.lower().strip()
        if not q or len(q) < 2:
            return []

        # 1. Coincidencia exacta (substring)
        exact = [p for p in self._cache if q in p["_nombre_lower"]]
        if exact:
            return exact[:max_results]

        # 2. Coincidencia por inicio de palabra
        starts = [p for p in self._cache
                  if any(w.startswith(q) for w in p["_nombre_lower"].split())]
        if starts:
            return starts[:max_results]

        # 3. Fuzzy matching (Levenshtein)
        scored: List[Tuple[int, Dict]] = []
        for p in self._cache:
            # Comparar contra cada palabra del nombre
            words = p["_nombre_lower"].split()
            min_dist = min((_levenshtein(q, w) for w in words), default=99)
            if min_dist <= FUZZY_MATCH_THRESHOLD:
                scored.append((min_dist, p))

        scored.sort(key=lambda x: x[0])
        return [p for _, p in scored[:max_results]]

    def match_single(self, name_raw: str) -> Optional[Dict]:
        """Intenta encontrar un único producto que coincida."""
        results = self.search(name_raw, max_results=1)
        return results[0] if results else None

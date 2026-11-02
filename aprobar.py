# -*- coding: utf-8 -*-
"""Aprueba en bloque intents, specs o planes del backlog SDLC.

Uso (desde la raíz del repo):
    python aprobar.py --etapa intent --simular
    python aprobar.py --etapa spec --prefijo SDLC-ARQ
    python aprobar.py --etapa plan --solo SDLC-ARQ-IDEM-001,SDLC-ARQ-INST-001
    python aprobar.py --etapa spec --prioridad P0 --excluir-con-preguntas

Qué cambia, por cada ítem elegido que esté en "<etapa>-borrador":
- En items/<ID>/<etapa>.md, la línea "- **Estado:** ..." pasa a "aprobado (<fecha>, <nombre>)".
- En BACKLOG.md, la etapa pasa de <etapa>-borrador a <etapa>-aprobado.
- Agrega una línea en "Decisiones aprobadas" con los IDs aprobados.
No hace commit: revisa con `git diff` y haz commit tú.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

SDLC = Path("pos_spj_v13.4/docs/sdlc")
ROW = re.compile(r"^\| \[(SDLC-[A-Z0-9-]+)\]\([^)]*\) \|([^|]*)\|")
OPEN_Q = re.compile(r"^- (SDLC-[A-Z0-9-]+(?:\s*/\s*SDLC-[A-Z0-9-]+)*) ·")


def ids_con_preguntas(lines: list[str]) -> set[str]:
    ids, dentro = set(), False
    for line in lines:
        if line.startswith("## "):
            dentro = line.startswith("## Preguntas abiertas")
            continue
        m = OPEN_Q.match(line) if dentro else None
        if m:
            ids.update(x.strip() for x in m.group(1).split("/"))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapa", choices=["intent", "spec", "plan"], required=True)
    ap.add_argument("--nombre", default="Alfred")
    ap.add_argument("--fecha", default=dt.date.today().isoformat())
    ap.add_argument("--prioridad", help="Lista separada por comas, p. ej. P0,P1")
    ap.add_argument("--prefijo", help="Solo IDs que empiecen así, p. ej. SDLC-ARQ")
    ap.add_argument("--solo", help="IDs separados por comas")
    ap.add_argument("--excluir-con-preguntas", action="store_true")
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()

    backlog = SDLC / "BACKLOG.md"
    if not backlog.exists():
        print(f"No encuentro {backlog}. Ejecuta el script desde la raíz del repo.")
        return 1
    desde, hacia = f"| {args.etapa}-borrador |", f"| {args.etapa}-aprobado |"
    lines = backlog.read_text(encoding="utf-8").splitlines()
    prioridades = {p.strip() for p in args.prioridad.split(",")} if args.prioridad else None
    solo = {s.strip() for s in args.solo.split(",")} if args.solo else None
    con_preguntas = ids_con_preguntas(lines) if args.excluir_con_preguntas else set()

    aprobados, omitidos = [], []
    for n, line in enumerate(lines):
        m = ROW.match(line)
        if not m or desde not in line:
            continue
        item_id, prioridad = m.group(1), m.group(2).strip()
        if solo and item_id not in solo:
            continue
        if args.prefijo and not item_id.startswith(args.prefijo):
            continue
        if prioridades and prioridad not in prioridades:
            continue
        if item_id in con_preguntas:
            omitidos.append(f"{item_id} (tiene preguntas abiertas)")
            continue
        archivo = SDLC / "items" / item_id / f"{args.etapa}.md"
        if not archivo.exists():
            omitidos.append(f"{item_id} (no existe {archivo})")
            continue
        texto = archivo.read_text(encoding="utf-8")
        nuevo, cambios = re.subn(
            r"^- \*\*Estado:\*\*.*$",
            f"- **Estado:** aprobado ({args.fecha}, {args.nombre})",
            texto, count=1, flags=re.MULTILINE)
        if not cambios:
            omitidos.append(f"{item_id} ({archivo.name} sin línea '- **Estado:**')")
            continue
        if not args.simular:
            archivo.write_text(nuevo, encoding="utf-8", newline="\n")
        lines[n] = line.replace(desde, hacia, 1)
        aprobados.append(item_id)

    if aprobados and not args.simular:
        registro = (f"- {args.fecha} · aprobación en bloque de {len(aprobados)} {args.etapa}s · "
                    f"{', '.join(aprobados)} · {args.nombre}")
        for n, line in enumerate(lines):
            if line.startswith("## Decisiones aprobadas"):
                pos = n + 1
                while pos < len(lines) and (not lines[pos].strip() or lines[pos].startswith("_(")):
                    pos += 1
                lines.insert(pos, registro)
                break
        backlog.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    modo = "SIMULACIÓN — no se cambió nada" if args.simular else "Listo"
    print(f"{modo}. Etapa: {args.etapa}. Aprobados: {len(aprobados)}. Omitidos: {len(omitidos)}.")
    for x in aprobados:
        print("  +", x)
    for x in omitidos:
        print("  -", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())

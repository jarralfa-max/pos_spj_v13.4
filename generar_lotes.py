# -*- coding: utf-8 -*-
"""Genera docs/sdlc/LOTES.md a partir de BACKLOG.md.

Uso, desde la raíz del repo:  python generar_lotes.py
Vuelve a correrlo cuando el backlog cambie (ítems nuevos, aprobaciones, dependencias).
"""
import re, sys, heapq
from collections import defaultdict
B = sys.argv[1] if len(sys.argv) > 1 else "pos_spj_v13.4/docs/sdlc/BACKLOG.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "pos_spj_v13.4/docs/sdlc/LOTES.md"
text = open(B, encoding='utf-8').read()
rows = {}; order = []
for l in text.splitlines():
    m = re.match(r"^\| \[(SDLC-[A-Z0-9-]+)\]\([^)]*\) \|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", l)
    if m:
        k = m.group(1)
        rows[k] = dict(p=m.group(2).strip(), t=m.group(3).strip(), title=m.group(4).strip(), st=m.group(6).strip(),
                       deps=[d for d in re.findall(r"SDLC-[A-Z0-9-]+", m.group(8)) if d != k])
        order.append(k)
q = set(); inq = False
for l in text.splitlines():
    if l.startswith('## '): inq = l.startswith('## Preguntas abiertas'); continue
    if inq and l.startswith('- SDLC'): q.update(re.findall(r"SDLC-[A-Z0-9-]+", l.split('·')[0]))
missing = {k: [d for d in v['deps'] if d not in rows] for k, v in rows.items() if any(d not in rows for d in v['deps'])}
for k in rows: rows[k]['deps'] = [d for d in rows[k]['deps'] if d in rows]
AREA = {'CASH':'Caja y turnos','ARQ-SHIFT':'Caja y turnos',
 'SALES':'Ventas y precios','ARQ-IDEM':'Ventas y precios','PRICE':'Ventas y precios','CRED':'Ventas y precios',
 'ARQ-PERM':'Permisos, sesiones y seguridad','ARQ-SCOPE':'Permisos, sesiones y seguridad','ARQ-SESS':'Permisos, sesiones y seguridad','SEC':'Permisos, sesiones y seguridad','ARQ-AUD':'Permisos, sesiones y seguridad',
 'ARQ-TERM':'Terminales y sincronización','ARQ-SYNC':'Terminales y sincronización','ARQ-HYB':'Terminales y sincronización','ARQ-OFF':'Terminales y sincronización','SYNC':'Terminales y sincronización',
 'INST':'Instalador y actualizador','ARQ-INST':'Instalador y actualizador',
 'INV':'Inventario, compras y producción','TRF':'Inventario, compras y producción','PROC':'Inventario, compras y producción','PROD':'Inventario, compras y producción','PUR':'Inventario, compras y producción','LOSS':'Inventario, compras y producción','LOG':'Inventario, compras y producción',
 'FIN':'Finanzas y RRHH','HR':'Finanzas y RRHH',
 'CORE':'Núcleo y configuración','ARQ-TEST':'Núcleo y configuración','SET':'Núcleo y configuración','BI':'Núcleo y configuración',
 'CRM':'Clientes y fidelidad','LOY':'Clientes y fidelidad',
 'WA':'WhatsApp','ASSET':'Activos','UI':'UI / Design System','PAY':'Mercado Pago','ORD':'Pedidos y repartos'}
def area(k):
    parts = k.split('-')[1:-1]
    for n in (2, 1):
        key = '-'.join(parts[:n])
        if key in AREA: return AREA[key]
    return 'Otros'
P = {'P0':0,'P1':1,'P2':2,'P3':3}
# cycle check
state = {}
def dfs(k, stack):
    state[k] = 1
    for d in rows[k]['deps']:
        if state.get(d) == 1: print("CICLO de dependencias:", " -> ".join(stack + [k, d]))
        elif not state.get(d): dfs(d, stack + [k])
    state[k] = 2
for k in rows:
    if not state.get(k): dfs(k, [])
# priority-aware topo per area, then chunk
byarea = defaultdict(list)
for k in rows: byarea[area(k)].append(k)
SIZE = 6
lots = []
for a, ks in byarea.items():
    ks_set = set(ks)
    indeg = {k: sum(1 for d in rows[k]['deps'] if d in ks_set) for k in ks}
    # effective priority: min priority of item and its in-area dependents (pull deps of P0 forward)
    eff = {k: P.get(rows[k]['p'], 3) for k in ks}
    changed = True
    while changed:
        changed = False
        for k in ks:
            for d in rows[k]['deps']:
                if d in ks_set and eff[d] > eff[k]: eff[d] = eff[k]; changed = True
    h = [(eff[k], P.get(rows[k]['p'], 3), k) for k in ks if indeg[k] == 0]; heapq.heapify(h)
    seq = []
    while h:
        _, _, k = heapq.heappop(h); seq.append(k)
        for j in ks:
            if k in rows[j]['deps']:
                indeg[j] -= 1
                if indeg[j] == 0: heapq.heappush(h, (eff[j], P.get(rows[j]['p'], 3), j))
    assert len(seq) == len(ks), a
    for i in range(0, len(seq), SIZE):
        lots.append(dict(area=a, items=seq[i:i+SIZE]))
where = {k: i for i, L in enumerate(lots) for k in L['items']}
rnd = {}
def R(i, seen=()):
    if i in rnd: return rnd[i]
    r = 1
    for k in lots[i]['items']:
        for d in rows[k]['deps']:
            j = where[d]
            if j != i and j not in seen: r = max(r, R(j, seen + (i,)) + 1)
    # same-area previous lot must also go first
    prev = [j for j in range(i) if lots[j]['area'] == lots[i]['area']]
    if prev: r = max(r, R(prev[-1], seen + (i,)) + 1)
    rnd[i] = r; return r
for i in range(len(lots)): R(i)
def best(L): return min(P.get(rows[k]['p'], 3) for k in L['items'])
idx = sorted(range(len(lots)), key=lambda i: (rnd[i], best(lots[i]), lots[i]['area']))
num = {i: n + 1 for n, i in enumerate(idx)}
def mark(k):
    st = rows[k]['st']
    if st in ('intent-borrador',): s = 'B'
    else: s = '✓'
    if k in q: s += '?'
    return s
o = []
o.append("# Lotes de corrección directa\n")
o.append("Generado desde `BACKLOG.md`. Cada lote agrupa ítems de una misma área (máximo 6), en orden de dependencias y prioridad. Se ejecuta con `/sdlc-corregir lote N` o, en paralelo, `/sdlc-corregir ronda N`.\n")
o.append("**Rondas:** los lotes de una misma ronda son de áreas distintas y no dependen entre sí, así que pueden correr al mismo tiempo, cada uno con su subagente y su rama `fix/lote-N`. Una ronda empieza cuando los PRs de las rondas anteriores ya están integrados en la rama base.\n")
o.append("**Marcas:** ✓ intent aprobado · B intent en borrador (apruébalo o el comando lo salta) · ? tiene pregunta abierta en el backlog (el comando lo intenta y lo bloquea si necesita la decisión).\n")
for r in sorted(set(rnd.values())):
    ls = [i for i in idx if rnd[i] == r]
    o.append(f"\n## Ronda {r} — {len(ls)} lotes\n")
    o.append("| Lote | Área | Ítems (en orden) | Listos |\n|---|---|---|---|")
    for i in ls:
        L = lots[i]
        its = ", ".join(f"{k} ({rows[k]['p']}{'·'+mark(k)})" for k in L['items'])
        ready = sum(1 for k in L['items'] if mark(k) == '✓')
        o.append(f"| {num[i]} | {L['area']} | {its} | {ready}/{len(L['items'])} |")
o.append("\n## Detalle por lote\n")
for i in idx:
    L = lots[i]
    o.append(f"### Lote {num[i]} — {L['area']} (ronda {rnd[i]})\n")
    for k in L['items']:
        dep = ", ".join(rows[k]['deps']) or "—"
        o.append(f"- `{k}` {rows[k]['p']} {rows[k]['t']} [{mark(k)}] — {rows[k]['title']} · depende de: {dep}")
    o.append("")
if missing: o.append("\n## Dependencias a ítems inexistentes\n" + "\n".join(f"- {k}: {v}" for k, v in missing.items()))
open(OUT, 'w', encoding='utf-8').write("\n".join(o) + "\n")
print("lotes", len(lots), "rondas", max(rnd.values()))
from collections import Counter
print(Counter(rnd.values()))
print(Counter(L['area'] for L in lots))
ready_items = sum(1 for k in rows if mark(k) == '✓')
print("ítems con intent aprobado:", ready_items)
print("Escrito:", OUT)

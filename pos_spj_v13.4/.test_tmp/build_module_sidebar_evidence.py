"""Build a local viewer for saved, unmodified Qt sidebar captures."""
import hashlib
import json
import struct
from pathlib import Path

package = Path(__file__).resolve().parents[1]
directory = package / "docs/refactor/evidence/module_sidebar_icons"
labels = {
    "finance": "Finanzas", "hr": "Recursos Humanos", "products": "Productos",
    "inventory": "Inventario", "pricing": "Precios", "purchasing": "Compras",
    "losses": "Merma", "meat_processing": "Procesamiento cárnico",
    "orders_delivery": "Pedidos y Delivery", "business_intelligence": "BI",
    "transfers": "Transferencias", "configuracion": "Configuración",
    "cash_register": "Caja", "customers_crm": "Clientes y CRM", "fidelidad": "Fidelidad",
    "tarjetas_fidelidad": "Tarjetas de fidelidad", "assets": "Activos",
}
records = []
for path in sorted(directory.glob("*.png")):
    module, theme, density, state = path.stem.rsplit("-", 3)
    blob = path.read_bytes()
    width, height = struct.unpack(">II", blob[16:24])
    records.append(dict(file=path.name, module=module, title=labels[module], theme=theme,
                        density=density, state=state, width=width, height=height,
                        sha256=hashlib.sha256(blob).hexdigest()))
assert len(records) == 168
assert len({record["module"] for record in records}) == 17
manifest = {
    "scope": "Actual Qt navigation widgets only; neutral business page bodies; no database.",
    "limitations": "768 px sidebar crops at scroll start; one largest-group flyout per grouped module. Not a full application or five-resolution matrix, nor an approved pixel baseline.",
    "modules": 17, "test_cases": 68, "sidebar_captures": 136, "flyout_captures": 32,
    "images": records,
}
(directory / "captures.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
html = '''<!doctype html>
<html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Iconos de las sidebars de módulos · SPJ</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f3;color:#202722;font:15px system-ui,sans-serif}
header{padding:28px clamp(18px,4vw,60px);background:#18372b;color:white}h1{margin:0 0 12px;font-size:26px}
p{line-height:1.6;max-width:1050px;margin:8px 0}header a{color:#f0d599}
nav{display:flex;flex-wrap:wrap;gap:20px;padding:20px clamp(18px,4vw,60px);background:white;border-bottom:1px solid #d4dad6;position:sticky;top:0;z-index:1}
label{display:grid;gap:6px;font-weight:600}select{font:inherit;min-width:140px;padding:8px;border:1px solid #69776e;border-radius:4px;background:white;color:#202722}
main{padding:18px clamp(18px,4vw,60px)}section{margin-bottom:36px}h2{font-size:21px;margin-bottom:8px}.rows{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
figure{margin:0;background:white;border:1px solid #d4dad6;border-radius:6px;padding:14px;max-width:100%;overflow:auto}
figcaption{font-weight:600;margin-bottom:12px}figcaption small{display:block;margin-top:5px;font-weight:400;color:#526258}
img{display:block;max-width:100%;height:auto}a:focus-visible,select:focus-visible{outline:3px solid #9d2927;outline-offset:3px}.count{margin:0 0 24px;color:#526258}
</style>
<header><h1>Iconos de navegación por módulo</h1>
<p>17 módulos · Claro y Oscuro · Cómoda y Táctil · Expandido y colapsado. 168 capturas PNG producidas por Qt: 136 sidebars y 32 menús de grupos.</p>
<p>Se usan los componentes reales con cuerpos de página neutrales y sin conexión a la base de datos. Cada sidebar se captura con 768 px de alto, al inicio del desplazamiento; las listas largas continúan fuera del recorte. El menú corresponde al grupo con más opciones. Estas imágenes no representan la aplicación completa ni la matriz de cinco resoluciones.</p>
<p>Haz clic en una imagen para abrirla en su tamaño original. <a href="captures.json">Inventario y SHA-256</a>.</p></header>
<nav aria-label="Filtros de evidencia">
<label>Módulo<select id="module"><option value="all">Todos</option></select></label>
<label>Tema<select id="theme"><option value="light">Claro</option><option value="dark">Oscuro</option><option value="all">Ambos</option></select></label>
<label>Densidad<select id="density"><option value="comfortable">Cómoda</option><option value="touch">Táctil</option><option value="all">Ambas</option></select></label>
<label>Estado<select id="state"><option value="all">Todos</option><option value="expanded">Expandido</option><option value="collapsed">Colapsado</option><option value="flyout">Menú de grupo</option></select></label>
</nav><main><p id="count" class="count" aria-live="polite"></p><div id="gallery"></div></main>
<script>
const records = __RECORDS__;
const labels = __LABELS__;
const selectors = ['module','theme','density','state'].map(id=>document.getElementById(id));
for(const [key,title] of Object.entries(labels)){const option=document.createElement('option');option.value=key;option.textContent=title;selectors[0].append(option)}
const stateNames={expanded:'Expandido',collapsed:'Colapsado',flyout:'Menú de grupo'};
const stateOrder={expanded:0,collapsed:1,flyout:2};
function render(){
 const visible=records.filter(record=>selectors.every(select=>select.value==='all'||record[select.id]===select.value));
 document.getElementById('count').textContent=`${visible.length} capturas visibles`;
 const gallery=document.getElementById('gallery');gallery.replaceChildren();
 for(const [module,title] of Object.entries(labels)){
  const items=visible.filter(item=>item.module===module).sort((a,b)=>(a.theme+a.density).localeCompare(b.theme+b.density)||stateOrder[a.state]-stateOrder[b.state]);
  if(!items.length)continue;
  const section=document.createElement('section');const heading=document.createElement('h2');heading.textContent=title;section.append(heading);
  const rows=document.createElement('div');rows.className='rows';section.append(rows);
  for(const item of items){
   const figure=document.createElement('figure');const caption=document.createElement('figcaption');
   caption.textContent=stateNames[item.state];const detail=document.createElement('small');
   detail.textContent=`${item.theme==='light'?'Claro':'Oscuro'} · ${item.density==='comfortable'?'Cómoda':'Táctil'} · ${item.width} × ${item.height} px`;caption.append(detail);figure.append(caption);
   const link=document.createElement('a');link.href=item.file;link.target='_blank';link.rel='noopener';const image=document.createElement('img');
   image.src=item.file;image.alt=`${title}: ${caption.textContent}`;image.loading='lazy';image.width=item.width;image.height=item.height;link.append(image);figure.append(link);rows.append(figure);
  }
  gallery.append(section);
 }
}
selectors.forEach(select=>select.addEventListener('change',render));render();
</script></html>
'''
html = html.replace("__RECORDS__", json.dumps(records, ensure_ascii=False)).replace("__LABELS__", json.dumps(labels, ensure_ascii=False))
(directory / "index.html").write_text(html, encoding="utf-8")
print(f"Generated viewer and manifest for {len(records)} Qt captures in {directory}")

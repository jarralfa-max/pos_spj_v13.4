import { LogisticsApi } from "./api.js";
import { localStore, createQueuedCommand } from "./store.js";
import { SyncEngine } from "./sync.js";
import { uuidv7 } from "./uuidv7.js";

const $ = (id) => document.getElementById(id);
const token = () => sessionStorage.getItem("spj-mobile-token");
const api = new LogisticsApi(token);
const sync = new SyncEngine(api, localStore);
const steps = ["documents", "containers", "contents", "review"];
let stepIndex = 0;
let scanStream = null;
let scanTimer = null;
let products = [];
let state = {
  session: null, selectedDocument: null, shipmentId: null, shipmentVersion: 0,
  nodes: [], contents: [], sealedNodeIds: [], photos: [],
};

function decimal(value) {
  const normalized = String(value ?? "").trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) throw new Error("Captura un número decimal válido");
  return normalized;
}

function addDecimalTexts(values, scale = 3) {
  const factor = 10n ** BigInt(scale);
  const total = values.reduce((sum, value) => {
    const [whole, fraction = ""] = String(value).split(".");
    return sum + BigInt(whole) * factor + BigInt(fraction.padEnd(scale, "0").slice(0, scale));
  }, 0n);
  const digits = total.toString().padStart(scale + 1, "0");
  return `${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
}

function toast(message) {
  const item = document.createElement("div"); item.className = "toast"; item.textContent = message;
  $("toastRegion").append(item); setTimeout(() => item.remove(), 4200);
}

function message(text, type = "") {
  const element = $("globalMessage"); element.textContent = text; element.className = `inline-state ${type}`; element.hidden = !text;
}

async function updateNetwork() {
  const online = navigator.onLine;
  $("networkBadge").textContent = online ? "En línea" : "Sin conexión";
  $("networkBadge").className = `badge ${online ? "online" : "offline"}`;
  const pending = await sync.pendingCount();
  $("syncBadge").textContent = `${pending} pendiente${pending === 1 ? "" : "s"}`;
  $("syncBadge").className = `badge ${pending ? "offline" : "online"}`;
  renderReview();
}

async function persistDraft() {
  if (!state.selectedDocument) return;
  await localStore.putDraft({ id: state.selectedDocument.id, state, updatedAt: new Date().toISOString() });
}

function showWorkspace(session) {
  state.session = session;
  $("loginView").hidden = true; $("workspaceView").hidden = false;
  $("sessionUser").textContent = session.displayName;
  $("sessionBranch").textContent = session.branchName;
  $("sessionWarehouse").textContent = session.warehouseName;
  void loadDocuments();
}

async function loadDocuments(query = "") {
  $("documentList").innerHTML = '<div class="inline-state">Cargando documentos…</div>';
  try {
    const response = await api.documents(query);
    renderDocuments(response.items || []);
  } catch (error) {
    $("documentList").innerHTML = `<div class="inline-state error">${error.message}</div>`;
  }
}

function renderDocuments(documents) {
  const list = $("documentList"); list.replaceChildren();
  if (!documents.length) { list.innerHTML = '<div class="inline-state">No hay documentos habilitados para carga.</div>'; return; }
  documents.forEach((documentItem) => {
    const button = document.createElement("button"); button.className = "document-card";
    button.innerHTML = `<strong>${documentItem.documentNumber}</strong><span>${documentItem.typeLabel}</span><span>${documentItem.supplierName}</span><span>${documentItem.lineCount} productos</span>`;
    button.addEventListener("click", () => selectDocument(documentItem, button)); list.append(button);
  });
}

async function selectDocument(documentItem, button) {
  document.querySelectorAll(".document-card").forEach((item) => item.classList.remove("selected"));
  button.classList.add("selected"); state.selectedDocument = documentItem;
  const stored = await localStore.getDraft(documentItem.id);
  if (stored?.state) state = { ...state, ...stored.state, session: state.session, selectedDocument: documentItem };
  products = (await api.products(documentItem.id)).items || [];
  $("productOptions").innerHTML = products.map((item) => `<option value="${item.code}">${item.name}</option>`).join("");
  renderTree(); renderContents(); await persistDraft(); toast("Documento seleccionado");
}

function showStep(name) {
  stepIndex = steps.indexOf(name);
  steps.forEach((step) => { $(`${step}Step`).hidden = step !== name; document.querySelector(`[data-step="${step}"]`).classList.toggle("active", step === name); });
  $("previousStep").disabled = stepIndex === 0; $("nextStep").hidden = stepIndex === steps.length - 1;
  if (name === "review") renderReview();
}

async function ensureShipment() {
  if (state.shipmentId) return;
  const operationId = uuidv7(); state.shipmentId = uuidv7(); state.shipmentVersion = 0;
  await sync.enqueue(createQueuedCommand({
    operationId, endpoint: "/logistics/mobile/shipments", aggregateVersion: 0,
    body: { shipmentId: state.shipmentId, documentType: state.selectedDocument.type,
      documentId: state.selectedDocument.id, supplierId: state.selectedDocument.supplierId },
  }));
}

async function addContainer(tokenValue, parentNodeId = null) {
  if (!state.selectedDocument) throw new Error("Selecciona primero un documento");
  await ensureShipment();
  let resolved;
  try {
    resolved = await api.resolveQr(tokenValue);
    await localStore.putContainer({ token: tokenValue, ...resolved, cachedAt: new Date().toISOString() });
  } catch (error) {
    resolved = await localStore.getContainer(tokenValue);
    if (!resolved) throw error;
    toast("Contenedor validado previamente; se agregará al borrador offline");
  }
  if (state.nodes.some((node) => node.containerId === resolved.containerId)) throw new Error("El contenedor ya está en el árbol");
  const node = { id: uuidv7(), containerId: resolved.containerId, code: resolved.containerCode,
    typeName: resolved.typeName, parentNodeId, status: "SYNC_PENDING" };
  const operationId = uuidv7(); state.nodes.push(node);
  await sync.enqueue(createQueuedCommand({ operationId,
    endpoint: `/logistics/mobile/shipments/${state.shipmentId}/nodes`,
    aggregateVersion: state.shipmentVersion,
    body: { nodeId: node.id, containerToken: tokenValue, parentNodeId },
  }));
  await persistDraft(); renderTree(); toast(`${resolved.containerCode} agregado`);
}

function renderTree() {
  const tree = $("containerTree"); tree.replaceChildren();
  const options = ['<option value="">Contenedor raíz</option>'];
  const nodesByParent = (parent) => state.nodes.filter((node) => node.parentNodeId === parent);
  const draw = (node, depth) => {
    const element = document.createElement("div"); element.className = "tree-node";
    element.classList.add(`tree-depth-${Math.min(depth, 5)}`); element.setAttribute("role", "treeitem");
    element.innerHTML = `<div class="node-title"><strong>${node.code}</strong><span class="badge">${node.status}</span></div><small>${node.typeName}</small>`;
    tree.append(element); options.push(`<option value="${node.id}">${"—".repeat(depth)} ${node.code}</option>`);
    nodesByParent(node.id).forEach((child) => draw(child, depth + 1));
  };
  nodesByParent(null).forEach((node) => draw(node, 0));
  $("parentNode").innerHTML = options.join(""); $("contentNode").innerHTML = options.slice(1).join("");
  if (!state.nodes.length) tree.innerHTML = '<div class="inline-state">Escanea un contenedor raíz para comenzar.</div>';
}

async function savePhotos(files, assignmentId) {
  const ids = [];
  for (const file of files) {
    const id = uuidv7(); await localStore.putPhoto({ id, assignmentId, blob: file, name: file.name, type: file.type }); ids.push(id);
  }
  return ids;
}

async function addContent(event) {
  event.preventDefault();
  const productInput = $("productSearch").value.trim();
  const product = products.find((item) => item.code === productInput || item.id === productInput);
  if (!product) throw new Error("Selecciona un producto del documento");
  const assignmentId = uuidv7();
  const photoIds = await savePhotos($("photoInput").files, assignmentId);
  const content = { id: assignmentId, nodeId: $("contentNode").value, productId: product.id,
    productName: product.name, sourceLineId: product.sourceLineId, quantity: decimal($("quantity").value),
    netWeight: decimal($("netWeight").value), unitCost: decimal($("unitCost").value),
    lotNumber: $("lotNumber").value.trim() || null, expirationDate: $("expirationDate").value || null,
    temperature: $("temperature").value ? decimal($("temperature").value) : null, photoIds,
    status: "SYNC_PENDING" };
  const operationId = uuidv7(); state.contents.push(content);
  await sync.enqueue(createQueuedCommand({ operationId,
    endpoint: `/logistics/mobile/shipments/${state.shipmentId}/contents`,
    aggregateVersion: state.shipmentVersion, body: content,
  }));
  for (const photoId of photoIds) {
    await sync.enqueue({ ...createQueuedCommand({ operationId: uuidv7(),
      endpoint: `/logistics/mobile/shipments/${state.shipmentId}/photos`,
      aggregateVersion: state.shipmentVersion, body: { assignmentId },
    }), photoId });
  }
  await persistDraft(); renderContents(); event.target.reset(); toast("Producto asignado");
}

function renderContents() {
  const list = $("contentList"); list.replaceChildren();
  state.contents.forEach((content) => {
    const node = state.nodes.find((item) => item.id === content.nodeId);
    const item = document.createElement("div"); item.className = "content-item";
    item.innerHTML = `<div><strong>${content.productName}</strong><small>${node?.code || "—"} · Lote ${content.lotNumber || "N/A"}</small></div><div><strong>${content.quantity}</strong><small>${content.netWeight} kg</small></div>`;
    list.append(item);
  });
}

function bottomUpNodes() { return [...state.nodes].sort((a, b) => depth(b) - depth(a)); }
function depth(node) { let result = 0; let cursor = node; while (cursor?.parentNodeId) { result += 1; cursor = state.nodes.find((item) => item.id === cursor.parentNodeId); } return result; }

async function sealNode(node) {
  if (state.nodes.some((child) => child.parentNodeId === node.id && !state.sealedNodeIds.includes(child.id))) throw new Error("Sella primero los contenedores hijos");
  const sealCode = prompt(`Código de sello para ${node.code}`); if (!sealCode) return;
  const operationId = uuidv7(); state.sealedNodeIds.push(node.id); node.status = "SEAL_PENDING";
  await sync.enqueue(createQueuedCommand({ operationId,
    endpoint: `/logistics/mobile/shipments/${state.shipmentId}/nodes/${node.id}/seal`,
    aggregateVersion: state.shipmentVersion, body: { sealCode, sealType: "MOBILE_CAPTURE" },
  }));
  await persistDraft(); renderReview();
}

async function renderReview() {
  if (!$("reviewSummary")) return;
  const totalWeight = addDecimalTexts(state.contents.map((item) => item.netWeight));
  $("reviewSummary").innerHTML = `<div class="summary-card"><small>Contenedores</small><strong>${state.nodes.length}</strong></div><div class="summary-card"><small>Productos</small><strong>${state.contents.length}</strong></div><div class="summary-card"><small>Peso neto</small><strong>${totalWeight} kg</strong></div>`;
  const list = $("sealList"); list.replaceChildren();
  bottomUpNodes().forEach((node) => {
    const sealed = state.sealedNodeIds.includes(node.id); const row = document.createElement("div"); row.className = "seal-item";
    row.innerHTML = `<div><strong>${node.code}</strong><small>${sealed ? "Sello pendiente de sincronización" : "Listo para sellar"}</small></div>`;
    const button = document.createElement("button"); button.className = sealed ? "ghost" : "secondary"; button.textContent = sealed ? "Sellado" : "Sellar"; button.disabled = sealed;
    button.addEventListener("click", () => sealNode(node).catch((error) => toast(error.message))); row.append(button); list.append(row);
  });
  const pending = await sync.pendingCount();
  $("dispatchButton").disabled = !$("dispatchConfirm").checked || !state.nodes.length || state.sealedNodeIds.length !== state.nodes.length || pending > 0 || !navigator.onLine;
}

async function dispatchShipment() {
  const pending = await sync.pendingCount();
  if (pending) throw new Error("Sincroniza todas las operaciones antes de despachar");
  const serverShipment = await api.shipment(state.shipmentId);
  state.shipmentVersion = serverShipment.version;
  const operationId = uuidv7();
  const result = await api.request(`/logistics/mobile/shipments/${state.shipmentId}/dispatch`, {
    method: "POST", body: {}, operationId, aggregateVersion: state.shipmentVersion,
  });
  state.shipmentVersion = result.version; toast("Embarque despachado correctamente");
}

async function startScanner() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("La cámara no está disponible");
  scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
  $("scannerVideo").srcObject = scanStream; await $("scannerVideo").play(); $("scannerPanel").hidden = false;
  if (!("BarcodeDetector" in window)) { toast("Escaneo automático no disponible; captura el token manualmente"); return; }
  const detector = new BarcodeDetector({ formats: ["qr_code"] });
  scanTimer = setInterval(async () => {
    const codes = await detector.detect($("scannerVideo")).catch(() => []);
    if (codes[0]?.rawValue) { stopScanner(); await addContainer(codes[0].rawValue, $("parentNode").value || null).catch((error) => toast(error.message)); }
  }, 450);
}

function stopScanner() { if (scanTimer) clearInterval(scanTimer); scanTimer = null; scanStream?.getTracks().forEach((track) => track.stop()); scanStream = null; $("scannerPanel").hidden = true; }

$("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault(); $("loginError").hidden = true;
  try {
    const session = await api.login({ username: $("username").value.trim(), password: $("password").value, deviceId: $("deviceId").value.trim() });
    sessionStorage.setItem("spj-mobile-token", session.accessToken); showWorkspace(session);
  } catch (error) { $("loginError").textContent = error.message; $("loginError").hidden = false; }
});
$("logoutButton").addEventListener("click", () => { if (state.nodes.length) { message("Hay un borrador local. Sincronízalo antes de cerrar sesión.", "warning"); return; } sessionStorage.clear(); location.reload(); });
$("refreshDocuments").addEventListener("click", () => loadDocuments($("documentSearch").value));
$("documentSearch").addEventListener("input", (event) => loadDocuments(event.target.value));
$("manualScanForm").addEventListener("submit", (event) => { event.preventDefault(); addContainer($("manualToken").value, $("parentNode").value || null).then(() => event.target.reset()).catch((error) => toast(error.message)); });
$("contentForm").addEventListener("submit", (event) => addContent(event).catch((error) => toast(error.message)));
$("scanButton").addEventListener("click", () => startScanner().catch((error) => toast(error.message))); $("stopScan").addEventListener("click", stopScanner);
$("previousStep").addEventListener("click", () => showStep(steps[Math.max(0, stepIndex - 1)]));
$("nextStep").addEventListener("click", () => { if (!state.selectedDocument) return toast("Selecciona un documento"); showStep(steps[Math.min(steps.length - 1, stepIndex + 1)]); });
document.querySelectorAll(".stepper button").forEach((button) => button.addEventListener("click", () => showStep(button.dataset.step)));
$("dispatchConfirm").addEventListener("change", renderReview); $("dispatchButton").addEventListener("click", () => dispatchShipment().catch((error) => toast(error.message)));
window.addEventListener("online", () => { updateNetwork(); sync.flush(); }); window.addEventListener("offline", updateNetwork); sync.addEventListener("change", updateNetwork);

if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js");
$("deviceId").value = localStorage.getItem("spj-device-id") || uuidv7(); localStorage.setItem("spj-device-id", $("deviceId").value);
showStep("documents"); updateNetwork();
if (token()) api.session().then(showWorkspace).catch(() => sessionStorage.removeItem("spj-mobile-token"));

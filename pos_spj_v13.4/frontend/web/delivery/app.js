import { DeliveryApi, ApiError } from "./api.js";
import { localStore, createQueuedCommand } from "./store.js";
import { SyncEngine } from "./sync.js";
import { uuidv7 } from "./uuidv7.js";

const STORAGE_KEY = "spj-delivery-session";
const STATUS_LABEL = {
  PENDING_ASSIGNMENT: "Sin asignar", ASSIGNED: "Asignado", READY_TO_DISPATCH: "Listo para despachar",
  DISPATCHED: "Despachado", IN_TRANSIT: "En camino", ARRIVED: "Llegó al destino",
  DELIVERY_ATTEMPT: "Registrando entrega", DELIVERED: "Entregado", FAILED: "Entrega fallida",
  REDELIVERY_PENDING: "Reentrega pendiente", RETURNING: "Regresando a sucursal",
  RETURNED_TO_BRANCH: "Devuelto a sucursal", CANCELLED: "Cancelado", CLOSED: "Cerrado",
};

let identity = null;
let api = null;
let sync = null;

const els = {};
function byId(id) { return document.getElementById(id); }

function loadSession() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); }
  catch { return null; }
}
function saveSession(value) {
  if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  else localStorage.removeItem(STORAGE_KEY);
}

function toast(message) {
  const region = byId("toastRegion");
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = message;
  region.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function updateNetworkBadge() {
  const badge = byId("networkBadge");
  badge.textContent = navigator.onLine ? "En línea" : "Sin conexión";
  badge.className = `badge ${navigator.onLine ? "online" : "offline"}`;
}

async function updateSyncBadge() {
  const pending = await sync.pendingCount();
  byId("syncBadge").textContent = `${pending} pendiente${pending === 1 ? "" : "s"}`;
}

function showView(view) {
  byId("loginView").hidden = view !== "login";
  byId("workspaceView").hidden = view !== "workspace";
}

async function doLogin(event) {
  event.preventDefault();
  const username = byId("username").value.trim();
  const password = byId("password").value;
  const deviceId = byId("deviceId").value.trim() || "phone-1";
  byId("loginError").hidden = true;
  try {
    const response = await api.login({ username, password, deviceId });
    identity = response;
    saveSession({ token: response.accessToken, deviceId: response.deviceId, userId: response.userId });
    afterLogin();
  } catch (error) {
    byId("loginError").hidden = false;
    byId("loginError").textContent = error instanceof ApiError && error.status === 401
      ? "Usuario o contraseña incorrectos" : "No se pudo iniciar sesión";
  }
}

function afterLogin() {
  byId("sessionUser").textContent = identity.displayName || identity.userId;
  byId("sessionBranch").textContent = identity.branchName || "—";
  showView("workspace");
  refreshAll();
}

function logout() {
  identity = null; saveSession(null); showView("login");
}

async function refreshAll() {
  await Promise.all([refreshPendingAssignments(), refreshJobs()]);
  await updateSyncBadge();
}

async function refreshPendingAssignments() {
  const container = byId("assignmentList");
  container.innerHTML = "";
  try {
    const { assignments } = await api.pendingAssignments();
    if (!assignments.length) {
      container.innerHTML = '<p class="empty">Sin asignaciones pendientes.</p>';
      return;
    }
    for (const assignment of assignments) container.appendChild(renderAssignmentCard(assignment));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return logout();
    container.innerHTML = '<p class="empty">No se pudo cargar (sin conexión).</p>';
  }
}

function renderAssignmentCard(assignment) {
  const card = document.createElement("div");
  card.className = "job-card";
  card.innerHTML = `
    <div class="job-card-head"><strong>Nueva asignación</strong><span class="badge">${assignment.status}</span></div>
    <p class="muted">Pedido de entrega #${assignment.deliveryJobId.slice(0, 8)}</p>
    <div class="job-actions">
      <button class="primary" data-action="accept">Aceptar</button>
      <button class="ghost" data-action="reject">Rechazar</button>
    </div>`;
  card.querySelector('[data-action="accept"]').onclick = () =>
    respondAssignment(assignment.assignmentId, "accept");
  card.querySelector('[data-action="reject"]').onclick = () =>
    respondAssignment(assignment.assignmentId, "reject");
  return card;
}

async function respondAssignment(assignmentId, action) {
  await runCommand(`/delivery/mobile/assignments/${assignmentId}/${action}`, {});
  await refreshAll();
}

async function refreshJobs() {
  const container = byId("jobList");
  container.innerHTML = "";
  try {
    const { jobs } = await api.jobs();
    if (!jobs.length) {
      container.innerHTML = '<p class="empty">Sin entregas activas.</p>';
      return;
    }
    for (const job of jobs) container.appendChild(renderJobCard(job));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return logout();
    container.innerHTML = '<p class="empty">No se pudo cargar (sin conexión).</p>';
  }
}

function renderJobCard(job) {
  const card = document.createElement("div");
  card.className = "job-card";
  const address = job.address
    ? [job.address.street, job.address.exteriorNumber, job.address.neighborhood].filter(Boolean).join(" ")
    : "Sin dirección registrada";
  card.innerHTML = `
    <div class="job-card-head">
      <strong>${job.orderNumber || job.deliveryJobId.slice(0, 8)}</strong>
      <span class="badge">${STATUS_LABEL[job.status] || job.status}</span>
    </div>
    <p class="muted">📍 ${address}</p>
    <p class="muted">${job.contactName || "Cliente"} · ${job.contactPhone || "sin teléfono"}</p>
    <p class="muted">💰 Cobrar: $${job.cashToCollect}</p>
    <div class="job-actions" data-actions></div>`;
  const actions = card.querySelector("[data-actions]");
  addStatusActions(actions, job);
  return card;
}

function addStatusActions(container, job) {
  const button = (label, cls, handler) => {
    const btn = document.createElement("button");
    btn.className = cls; btn.textContent = label; btn.onclick = handler;
    container.appendChild(btn);
  };
  if (job.status === "ASSIGNED") {
    button("Despachar", "primary", () => runJobAction(job.deliveryJobId, "dispatch"));
  } else if (job.status === "DISPATCHED") {
    button("Salir a ruta", "primary", () => runJobAction(job.deliveryJobId, "depart"));
  } else if (job.status === "IN_TRANSIT") {
    button("Llegué", "primary", () => runJobAction(job.deliveryJobId, "arrive"));
  } else if (job.status === "ARRIVED") {
    button("Registrar entrega", "primary", () => openAttemptForm(job));
    button("Reportar problema", "ghost", () => openAttemptForm(job, false));
  }
}

async function runJobAction(deliveryJobId, action) {
  await runCommand(`/delivery/mobile/jobs/${deliveryJobId}/${action}`, {});
  await refreshAll();
}

function openAttemptForm(job, successful = true) {
  const recipientName = successful ? window.prompt("Nombre de quien recibe:") : null;
  if (successful && !recipientName) return;
  const failureReason = successful ? null : window.prompt("Motivo de la falla:");
  if (!successful && !failureReason) return;
  runCommand(`/delivery/mobile/jobs/${job.deliveryJobId}/attempts`, {
    successful, recipientName, signatureReference: null, photoReference: null,
    pinVerified: false, latitude: null, longitude: null, notes: null, failureReason,
  }).then(refreshAll);
}

async function runCommand(endpoint, extra) {
  const operationId = uuidv7();
  const command = createQueuedCommand({
    operationId, endpoint, body: extra,
    identity: { userId: identity.userId, deviceId: identity.deviceId },
  });
  await sync.enqueue(command);
  await updateSyncBadge();
  if (!navigator.onLine) toast("Guardado sin conexión — se enviará al reconectar");
}

async function bootstrap() {
  const session = loadSession();
  api = new DeliveryApi(() => session?.token || identity?.accessToken || null);
  sync = new SyncEngine(api, localStore);
  sync.addEventListener("change", updateSyncBadge);
  window.addEventListener("online", () => { updateNetworkBadge(); sync.flush(); });
  window.addEventListener("offline", updateNetworkBadge);
  window.addEventListener("mobile-session-expired", logout);
  updateNetworkBadge();

  byId("loginForm").addEventListener("submit", doLogin);
  byId("logoutButton").addEventListener("click", logout);
  byId("refreshButton").addEventListener("click", refreshAll);

  if (session?.token) {
    api = new DeliveryApi(() => session.token);
    try {
      const me = await api.session();
      identity = { ...me, accessToken: session.token };
      afterLogin();
      return;
    } catch { saveSession(null); }
  }
  showView("login");

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
}

bootstrap();

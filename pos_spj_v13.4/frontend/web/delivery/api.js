const API_ROOT = "/api";

export class ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message); this.status = status; this.payload = payload;
  }
}

// No `aggregateVersion`/`If-Match` here (unlike the sibling
// `frontend/web/logistics/api.js`) — Pedidos/Delivery's aggregates carry no
// optimistic-concurrency version field, only `Idempotency-Key`.
export class DeliveryApi {
  constructor(getToken) { this.getToken = getToken; }

  async request(path, { method = "GET", body, operationId, signal } = {}) {
    const token = this.getToken();
    const headers = { Accept: "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (operationId) headers["Idempotency-Key"] = operationId;
    let response;
    try {
      response = await fetch(`${API_ROOT}${path}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal,
      });
    } catch (error) {
      throw new ApiError("Sin conexión con el servidor", 0, error);
    }
    const payload = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401) window.dispatchEvent(new CustomEvent("mobile-session-expired"));
      throw new ApiError(payload?.message || payload?.detail || "Error del servidor", response.status, payload);
    }
    return payload;
  }

  login(credentials) { return this.request("/mobile/session", { method: "POST", body: credentials }); }
  session() { return this.request("/mobile/session/me"); }
  jobs() { return this.request("/delivery/mobile/jobs"); }
  pendingAssignments() { return this.request("/delivery/mobile/assignments/pending"); }
}

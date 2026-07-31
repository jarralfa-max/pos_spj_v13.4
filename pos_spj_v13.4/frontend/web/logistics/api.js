const API_ROOT = "/api";

export class ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message); this.status = status; this.payload = payload;
  }
}

export class LogisticsApi {
  constructor(getToken) { this.getToken = getToken; }

  async request(path, { method = "GET", body, operationId, aggregateVersion, signal } = {}) {
    const token = this.getToken();
    const headers = { Accept: "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (operationId) headers["Idempotency-Key"] = operationId;
    if (aggregateVersion !== undefined) headers["If-Match"] = String(aggregateVersion);
    let response;
    try {
      response = await fetch(`${API_ROOT}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal });
    } catch (error) {
      throw new ApiError("Sin conexión con el servidor", 0, error);
    }
    const payload = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(payload?.detail || "Error del servidor", response.status, payload);
    return payload;
  }

  login(credentials) { return this.request("/mobile/session", { method: "POST", body: credentials }); }
  session() { return this.request("/mobile/session/me"); }
  documents(query = "") { return this.request(`/procurement/mobile/documents?q=${encodeURIComponent(query)}`); }
  products(documentId, query = "") { return this.request(`/procurement/mobile/documents/${documentId}/products?q=${encodeURIComponent(query)}`); }
  resolveQr(token) { return this.request(`/logistics/containers/resolve?token=${encodeURIComponent(token)}`); }
  shipment(id) { return this.request(`/logistics/shipments/${id}`); }
}

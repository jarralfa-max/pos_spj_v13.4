import { ApiError } from "./api.js";

export class SyncEngine extends EventTarget {
  constructor(api, store) { super(); this.api = api; this.store = store; this.running = false; }

  async pendingCount() {
    return (await this.store.listCommands()).filter((item) => ["PENDING", "RETRY"].includes(item.status)).length;
  }

  async enqueue(command) {
    const existing = await this.store.getCommand(command.operationId);
    if (existing) return existing;
    await this.store.putCommand(command);
    this.dispatchEvent(new CustomEvent("change"));
    if (navigator.onLine) void this.flush();
    return command;
  }

  async flush() {
    if (this.running || !navigator.onLine) return;
    this.running = true;
    try {
      const commands = (await this.store.listCommands())
        .filter((item) => ["PENDING", "RETRY"].includes(item.status))
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
      const serverVersions = new Map();
      for (const command of commands) {
        try {
          let body = command.body;
          if (command.photoId) {
            const photo = await this.store.getPhoto(command.photoId);
            if (!photo) throw new Error("Evidencia fotográfica local no encontrada");
            body = { ...body, contentBase64: await blobToBase64(photo.blob),
              fileName: photo.name, contentType: photo.type };
          }
          const aggregateKey = command.endpoint.match(/\/shipments\/([^/]+)/)?.[1] || command.body?.shipmentId;
          const expectedVersion = serverVersions.get(aggregateKey) ?? command.aggregateVersion;
          const result = await this.api.request(command.endpoint, {
            method: command.method, body, operationId: command.operationId,
            aggregateVersion: expectedVersion,
          });
          if (aggregateKey && result?.version !== undefined) serverVersions.set(aggregateKey, result.version);
          await this.store.putCommand({ ...command, status: "SYNCED", result, syncedAt: new Date().toISOString() });
        } catch (error) {
          const conflict = error instanceof ApiError && [409, 412].includes(error.status);
          const permanent = error instanceof ApiError && error.status >= 400 && error.status < 500 && !conflict;
          await this.store.putCommand({
            ...command, attempts: command.attempts + 1,
            status: conflict ? "CONFLICT" : permanent ? "REJECTED" : "RETRY",
            lastError: error.message,
          });
          // Critical commands remain ordered. Never last-write-wins or skip a conflict.
          if (conflict || !permanent) break;
        }
        this.dispatchEvent(new CustomEvent("change"));
      }
    } finally {
      this.running = false;
      this.dispatchEvent(new CustomEvent("change"));
    }
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob);
  });
}

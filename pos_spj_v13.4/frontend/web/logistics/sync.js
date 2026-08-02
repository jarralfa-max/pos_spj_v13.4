import { ApiError } from "./api.js";

export class SyncEngine extends EventTarget {
  constructor(api, store) { super(); this.api = api; this.store = store; this.running = false; }

<<<<<<< HEAD
  async pendingCount(shipmentId = null) {
    return (await this.store.listCommands()).filter((item) =>
      ["PENDING", "RETRY"].includes(item.status) && (!shipmentId || commandAggregate(item) === shipmentId)).length;
  }

  async conflicts(shipmentId = null) {
    return (await this.store.listCommands()).filter((item) =>
      item.status === "CONFLICT" && (!shipmentId || commandAggregate(item) === shipmentId));
  }

  async retryConflict(operationId, serverVersion) {
    const command = await this.store.getCommand(operationId);
    if (!command || command.status !== "CONFLICT") throw new Error("Conflicto inexistente");
    await this.store.putCommand({ ...command, status: "RETRY", aggregateVersion: serverVersion,
      lastError: null });
    this.dispatchEvent(new CustomEvent("change"));
    return this.flush();
=======
  async pendingCount() {
    return (await this.store.listCommands()).filter((item) => ["PENDING", "RETRY"].includes(item.status)).length;
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
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
<<<<<<< HEAD
          const aggregateKey = commandAggregate(command);
          const storedAggregate = aggregateKey ? await this.store.getAggregate(aggregateKey) : null;
          const expectedVersion = serverVersions.get(aggregateKey) ?? storedAggregate?.version ?? command.aggregateVersion;
=======
          const aggregateKey = command.endpoint.match(/\/shipments\/([^/]+)/)?.[1] || command.body?.shipmentId;
          const expectedVersion = serverVersions.get(aggregateKey) ?? command.aggregateVersion;
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
          const result = await this.api.request(command.endpoint, {
            method: command.method, body, operationId: command.operationId,
            aggregateVersion: expectedVersion,
          });
<<<<<<< HEAD
          if (aggregateKey && result?.version !== undefined) {
            serverVersions.set(aggregateKey, result.version);
            await this.store.putAggregate({ id: aggregateKey, version: result.version,
              updatedAt: new Date().toISOString() });
          }
          await this.store.putCommand({ ...command, status: "SYNCED", result, syncedAt: new Date().toISOString() });
        } catch (error) {
          const conflict = error instanceof ApiError && [409, 412].includes(error.status);
          const authentication = error instanceof ApiError && error.status === 401;
          const permanent = error instanceof ApiError && error.status >= 400 && error.status < 500 &&
            !conflict && !authentication;
=======
          if (aggregateKey && result?.version !== undefined) serverVersions.set(aggregateKey, result.version);
          await this.store.putCommand({ ...command, status: "SYNCED", result, syncedAt: new Date().toISOString() });
        } catch (error) {
          const conflict = error instanceof ApiError && [409, 412].includes(error.status);
          const permanent = error instanceof ApiError && error.status >= 400 && error.status < 500 && !conflict;
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
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

<<<<<<< HEAD
function commandAggregate(command) {
  return command.endpoint.match(/\/shipments\/([^/]+)/)?.[1] || command.body?.shipmentId || null;
}

=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob);
  });
}

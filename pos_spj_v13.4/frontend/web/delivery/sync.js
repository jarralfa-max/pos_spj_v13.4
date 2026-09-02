import { ApiError } from "./api.js";

// Simplified sibling of `frontend/web/logistics/sync.js` — no aggregate-
// version/CONFLICT state, since this router has no `If-Match` concept.
// PENDING/RETRY commands flush in creation order; a 4xx (other than 401)
// is REJECTED permanently rather than retried forever.
export class SyncEngine extends EventTarget {
  constructor(api, store) { super(); this.api = api; this.store = store; this.running = false; }

  async pendingCount() {
    return (await this.store.listCommands()).filter((item) =>
      ["PENDING", "RETRY"].includes(item.status)).length;
  }

  async rejected() {
    return (await this.store.listCommands()).filter((item) => item.status === "REJECTED");
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
      for (const command of commands) {
        try {
          const result = await this.api.request(command.endpoint, {
            method: command.method, body: command.body, operationId: command.operationId,
          });
          await this.store.putCommand({
            ...command, status: "SYNCED", result, syncedAt: new Date().toISOString(),
          });
        } catch (error) {
          const authentication = error instanceof ApiError && error.status === 401;
          const permanent = error instanceof ApiError && error.status >= 400 && error.status < 500
            && !authentication;
          await this.store.putCommand({
            ...command, attempts: command.attempts + 1,
            status: permanent ? "REJECTED" : "RETRY",
            lastError: error.message,
          });
          // Keep actions on the SAME job ordered — never skip ahead of a
          // still-pending step for that job.
          if (!permanent) break;
        }
        this.dispatchEvent(new CustomEvent("change"));
      }
    } finally {
      this.running = false;
      this.dispatchEvent(new CustomEvent("change"));
    }
  }
}

const DB_NAME = "spj-delivery-pwa";
const DB_VERSION = 1;

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("commands")) {
        const commands = db.createObjectStore("commands", { keyPath: "operationId" });
        commands.createIndex("status", "status");
        commands.createIndex("createdAt", "createdAt");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transact(storeName, mode, action) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const store = transaction.objectStore(storeName);
    const request = action(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => db.close();
  });
}

export const localStore = {
  putCommand: (command) => transact("commands", "readwrite", (store) => store.put(command)),
  getCommand: (id) => transact("commands", "readonly", (store) => store.get(id)),
  listCommands: () => transact("commands", "readonly", (store) => store.getAll()),
};

// No `aggregateVersion` here (unlike the sibling logistics PWA's
// `createQueuedCommand`) — see api.js's own note on why.
export function createQueuedCommand({ operationId, endpoint, method = "POST", body, identity }) {
  if (!operationId || !identity?.userId || !identity?.deviceId)
    throw new Error("Comando offline sin identidad o dispositivo");
  const createdAt = new Date().toISOString();
  return {
    operationId, endpoint, method,
    body: { ...body, clientOperationId: operationId, deviceId: identity.deviceId,
      userId: identity.userId, createdAt, payloadVersion: 1 },
    status: "PENDING", attempts: 0, createdAt, lastError: null,
  };
}

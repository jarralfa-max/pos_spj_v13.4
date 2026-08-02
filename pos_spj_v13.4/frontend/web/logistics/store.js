const DB_NAME = "spj-logistics-pwa";
<<<<<<< HEAD
const DB_VERSION = 3;
=======
const DB_VERSION = 2;
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("drafts")) db.createObjectStore("drafts", { keyPath: "id" });
      if (!db.objectStoreNames.contains("commands")) {
        const commands = db.createObjectStore("commands", { keyPath: "operationId" });
        commands.createIndex("status", "status");
        commands.createIndex("createdAt", "createdAt");
      }
      if (!db.objectStoreNames.contains("photos")) db.createObjectStore("photos", { keyPath: "id" });
      if (!db.objectStoreNames.contains("containers")) db.createObjectStore("containers", { keyPath: "token" });
<<<<<<< HEAD
      if (!db.objectStoreNames.contains("aggregates")) db.createObjectStore("aggregates", { keyPath: "id" });
=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
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
  putDraft: (draft) => transact("drafts", "readwrite", (store) => store.put(draft)),
  getDraft: (id) => transact("drafts", "readonly", (store) => store.get(id)),
  putCommand: (command) => transact("commands", "readwrite", (store) => store.put(command)),
  getCommand: (id) => transact("commands", "readonly", (store) => store.get(id)),
  listCommands: () => transact("commands", "readonly", (store) => store.getAll()),
  putPhoto: (photo) => transact("photos", "readwrite", (store) => store.put(photo)),
  getPhoto: (id) => transact("photos", "readonly", (store) => store.get(id)),
  putContainer: (item) => transact("containers", "readwrite", (store) => store.put(item)),
  getContainer: (token) => transact("containers", "readonly", (store) => store.get(token)),
<<<<<<< HEAD
  putAggregate: (item) => transact("aggregates", "readwrite", (store) => store.put(item)),
  getAggregate: (id) => transact("aggregates", "readonly", (store) => store.get(id)),
};

export function createQueuedCommand({ operationId, endpoint, method = "POST", body,
  aggregateVersion, identity }) {
  if (!operationId || aggregateVersion === undefined || !identity?.userId || !identity?.deviceId)
    throw new Error("Comando offline sin identidad, dispositivo o versión");
  const createdAt = new Date().toISOString();
  return {
    operationId, endpoint, method,
    body: { ...body, clientOperationId: operationId, deviceId: identity.deviceId,
      userId: identity.userId, createdAt, payloadVersion: 1 }, aggregateVersion,
    status: "PENDING", attempts: 0, createdAt, lastError: null,
=======
};

export function createQueuedCommand({ operationId, endpoint, method = "POST", body, aggregateVersion }) {
  if (!operationId || aggregateVersion === undefined) throw new Error("Comando offline sin identidad o versión");
  return {
    operationId, endpoint, method, body, aggregateVersion,
    status: "PENDING", attempts: 0, createdAt: new Date().toISOString(), lastError: null,
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
  };
}

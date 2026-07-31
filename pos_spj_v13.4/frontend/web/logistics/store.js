const DB_NAME = "spj-logistics-pwa";
const DB_VERSION = 2;

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
};

export function createQueuedCommand({ operationId, endpoint, method = "POST", body, aggregateVersion }) {
  if (!operationId || aggregateVersion === undefined) throw new Error("Comando offline sin identidad o versión");
  return {
    operationId, endpoint, method, body, aggregateVersion,
    status: "PENDING", attempts: 0, createdAt: new Date().toISOString(), lastError: null,
  };
}

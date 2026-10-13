// O que o app guarda no aparelho para funcionar sem o servidor: a fila de
// envio (lib/outbox.js) e a copia do cache de leitura (lib/queryPersist.js).
// IndexedDB, um banco, duas gavetas. Sem IndexedDB (aba privada antiga), cai
// para a memoria: o app segue funcionando, so nao lembra de nada ao fechar.
const DB_NAME = 'financas-offline'
const DB_VERSION = 1
export const OUTBOX_STORE = 'outbox'
export const CACHE_STORE = 'cache'

let dbPromise = null
const memory = { [OUTBOX_STORE]: new Map(), [CACHE_STORE]: new Map() }

function openDb() {
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve) => {
    if (typeof indexedDB === 'undefined') {
      resolve(null)
      return
    }
    let request
    try {
      request = indexedDB.open(DB_NAME, DB_VERSION)
    } catch {
      resolve(null)
      return
    }
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(OUTBOX_STORE)) db.createObjectStore(OUTBOX_STORE, { keyPath: 'client_id' })
      if (!db.objectStoreNames.contains(CACHE_STORE)) db.createObjectStore(CACHE_STORE, { keyPath: 'key' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => resolve(null)
    request.onblocked = () => resolve(null)
  })
  return dbPromise
}

const keyOf = (store, value) => (store === OUTBOX_STORE ? value.client_id : value.key)

async function run(store, mode, action, fallback) {
  const db = await openDb()
  if (!db) return fallback()
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(store, mode)
    const request = action(transaction.objectStore(store))
    transaction.oncomplete = () => resolve(request?.result)
    transaction.onerror = () => reject(transaction.error)
    transaction.onabort = () => reject(transaction.error)
  })
}

export function storeAll(store) {
  return run(store, 'readonly', (os) => os.getAll(), () => [...memory[store].values()])
}

export function storeGet(store, key) {
  return run(store, 'readonly', (os) => os.get(key), () => memory[store].get(key))
}

export function storePut(store, value) {
  return run(store, 'readwrite', (os) => os.put(value), () => { memory[store].set(keyOf(store, value), value) })
}

export function storeDelete(store, key) {
  return run(store, 'readwrite', (os) => os.delete(key), () => { memory[store].delete(key) })
}

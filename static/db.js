const dbPromise = idb.openDB('pos-db', 2, {
  upgrade(db, oldVersion) {
    if (!db.objectStoreNames.contains('pending-sales')) {
      db.createObjectStore('pending-sales', { keyPath: 'id', autoIncrement: true });
    }
    if (oldVersion < 2) {
        if (!db.objectStoreNames.contains('pending-collections')) {
            db.createObjectStore('pending-collections', { keyPath: 'id', autoIncrement: true });
        }
    }
  },
});

async function saveSale(sale) {
  const db = await dbPromise;
  const tx = db.transaction('pending-sales', 'readwrite');
  tx.store.add(sale);
  await tx.done;
}

async function getPendingSales() {
  const db = await dbPromise;
  return db.getAll('pending-sales');
}

async function clearPendingSales() {
  const db = await dbPromise;
  const tx = db.transaction('pending-sales', 'readwrite');
  tx.store.clear();
  await tx.done;
}

async function saveCollection(collection) {
    const db = await dbPromise;
    const tx = db.transaction('pending-collections', 'readwrite');
    tx.store.add(collection);
    await tx.done;
}

async function getPendingCollections() {
    const db = await dbPromise;
    return db.getAll('pending-collections');
}

async function clearPendingCollections() {
    const db = await dbPromise;
    const tx = db.transaction('pending-collections', 'readwrite');
    tx.store.clear();
    await tx.done;
}

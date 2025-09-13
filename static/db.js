// db.js
// Make sure you have included idb library before using this file
// <script src="https://cdn.jsdelivr.net/npm/idb@7/build/iife/index-min.js"></script>

// Open or upgrade IndexedDB
const dbPromise = idb.openDB('pos-db', 3, {
  upgrade(db, oldVersion) {
    console.log(`Upgrading database from version ${oldVersion}...`);

    if (!db.objectStoreNames.contains('pending-sales')) {
      db.createObjectStore('pending-sales', { keyPath: 'id', autoIncrement: true });
    }

    if (!db.objectStoreNames.contains('pending-collections')) {
      db.createObjectStore('pending-collections', { keyPath: 'id', autoIncrement: true });
    }

    if (!db.objectStoreNames.contains('products')) {
      db.createObjectStore('products', { keyPath: 'id' });
    }

    if (!db.objectStoreNames.contains('meals')) {
      db.createObjectStore('meals', { keyPath: 'id' });
    }

    if (!db.objectStoreNames.contains('dishes')) {
      db.createObjectStore('dishes', { keyPath: 'id' });
    }
  },
});

async function saveToStore(storeName, data) {
  const db = await dbPromise;
  const tx = db.transaction(storeName, 'readwrite');
  tx.store.put(data); 
  await tx.done;
  console.log(`Saved to ${storeName}:`, data);
}

async function getAllFromStore(storeName) {
  const db = await dbPromise;
  return db.getAll(storeName);
}

async function clearStore(storeName) {
  const db = await dbPromise;
  const tx = db.transaction(storeName, 'readwrite');
  await tx.store.clear();
  await tx.done;
  console.log(`Cleared store: ${storeName}`);
}

async function deleteFromStore(storeName, id) {
  const db = await dbPromise;
  const tx = db.transaction(storeName, 'readwrite');
  await tx.store.delete(id);
  await tx.done;
  console.log(`Deleted record with id ${id} from ${storeName}`);
}

async function saveSale(sale) {
  return saveToStore('pending-sales', sale);
}

async function getPendingSales() {
  return getAllFromStore('pending-sales');
}

async function clearPendingSales() {
  return clearStore('pending-sales');
}


async function saveCollection(collection) {
  return saveToStore('pending-collections', collection);
}

async function getPendingCollections() {
  return getAllFromStore('pending-collections');
}

async function clearPendingCollections() {
  return clearStore('pending-collections');
}


async function saveProduct(product) {
  return saveToStore('products', product);
}

async function getAllProducts() {
  return getAllFromStore('products');
}

async function clearProducts() {
  return clearStore('products');
}

async function deleteProduct(id) {
  return deleteFromStore('products', id);
}


async function saveMeal(meal) {
  return saveToStore('meals', meal);
}

async function getAllMeals() {
  return getAllFromStore('meals');
}

async function clearMeals() {
  return clearStore('meals');
}

async function deleteMeal(id) {
  return deleteFromStore('meals', id);
}


async function saveDish(dish) {
  return saveToStore('dishes', dish);
}

async function getAllDishes() {
  return getAllFromStore('dishes');
}

async function clearDishes() {
  return clearStore('dishes');
}

async function deleteDish(id) {
  return deleteFromStore('dishes', id);
}


// ===============================
// Example Usage (Comment out in production)
// ===============================
/*
(async () => {
  // Add a product
  await saveProduct({ id: 1, name: 'Coca-Cola', price: 2.5, stock: 50 });

  // Fetch all products
  const products = await getAllProducts();
  console.log('Products:', products);

  // Add a meal
  await saveMeal({ id: 1, name: 'Burger', price: 5.0 });

  // Fetch all meals
  const meals = await getAllMeals();
  console.log('Meals:', meals);

  // Add a dish
  await saveDish({ id: 1, name: 'Chicken Alfredo', ingredients: ['chicken', 'pasta', 'cream'] });

  // Fetch all dishes
  const dishes = await getAllDishes();
  console.log('Dishes:', dishes);

  // Clear all products
  // await clearProducts();
})();
*/

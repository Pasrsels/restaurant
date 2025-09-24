// Offline receipt handling
let lastReceiptNumber = null;
let offlineReceiptCount = 0;

async function initReceiptDB() {
    const request = indexedDB.open('POSOfflineDB', 1);
    
    request.onupgradeneeded = (event) => {
        const db = event.target.result;
        
        // Store for sales
        if (!db.objectStoreNames.contains('sales')) {
            const salesStore = db.createObjectStore('sales', { keyPath: 'id' });
            salesStore.createIndex('receipt_number', 'receipt_number', { unique: true });
            salesStore.createIndex('timestamp', 'timestamp');
            salesStore.createIndex('synced', 'synced');
        }
        
        // Store for receipt counter
        if (!db.objectStoreNames.contains('receipt_counter')) {
            db.createObjectStore('receipt_counter', { keyPath: 'id' });
        }
    };
    
    return new Promise((resolve, reject) => {
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            db = request.result;
            resolve(db);
        };
    });
}

// Fetch and store last receipt number from server
async function fetchLastReceiptNumber() {
    try {
        const response = await fetch('/api/sales/last-receipt-number/');
        if (response.ok) {
            const data = await response.json();
            lastReceiptNumber = data.last_receipt_number;
            
            // Store in IndexedDB
            const transaction = db.transaction(['receipt_counter'], 'readwrite');
            const store = transaction.objectStore('receipt_counter');
            await store.put({
                id: 'last_receipt',
                number: lastReceiptNumber,
                timestamp: new Date().toISOString()
            });
            
            return lastReceiptNumber;
        }
    } catch (error) {
        console.error('Failed to fetch last receipt number:', error);
    }
    
    // If fetch fails, try to get from IndexedDB
    return getLastStoredReceiptNumber();
}

// Get last stored receipt number from IndexedDB
async function getLastStoredReceiptNumber() {
    const transaction = db.transaction(['receipt_counter'], 'readonly');
    const store = transaction.objectStore('receipt_counter');
    
    return new Promise((resolve) => {
        const request = store.get('last_receipt');
        request.onsuccess = () => {
            const record = request.result;
            lastReceiptNumber = record ? record.number : 0;
            resolve(lastReceiptNumber);
        };
    });
}

// Generate next receipt number
async function generateReceiptNumber() {
    if (lastReceiptNumber === null) {
        await fetchLastReceiptNumber();
    }
    
    const nextNumber = lastReceiptNumber + offlineReceiptCount + 1;
    offlineReceiptCount++;
    
    // Format the receipt number
    const paddedNumber = nextNumber.toString().padStart(8, '0');
    const today = new Date();
    const year = today.getFullYear();
    const month = (today.getMonth() + 1).toString().padStart(2, '0');
    const day = today.getDate().toString().padStart(2, '0');
    
    return `RCP${year}${month}${day}${paddedNumber}`;
}

// Process offline sale with receipt
async function processOfflineSale(saleData) {
    const receiptNumber = await generateReceiptNumber();
    
    const sale = {
        id: generateUUID(),
        ...saleData,
        receipt_number: receiptNumber,
        timestamp: new Date().toISOString(),
        synced: false
    };
    
    // Save to IndexedDB
    await saveSaleLocally(sale);
    await addPendingOperation('sale', sale);
    
    // Generate and show receipt
    showReceipt(sale);
    
    if (isOnline) {
        syncSales();
    }
    
    return sale;
}

// Show receipt
function showReceipt(sale) {
    const receiptHTML = generateReceiptHTML(sale);
    
    // Create a new window for the receipt
    const receiptWindow = window.open('', 'Receipt', 'width=300,height=600');
    receiptWindow.document.write(receiptHTML);
    
    // Print automatically if needed
    if (shouldAutoPrint) {
        receiptWindow.print();
    }
}

function generateReceiptHTML(sale) {
    const date = new Date(sale.timestamp);
    return `
        <!DOCTYPE html>
        <html>
        <head>
            <title>Receipt ${sale.receipt_number}</title>
            <style>
                body {
                    font-family: monospace;
                    width: 300px;
                    margin: 0 auto;
                    padding: 10px;
                }
                .header, .footer {
                    text-align: center;
                    margin: 10px 0;
                }
                .receipt-number {
                    font-weight: bold;
                }
                .offline-notice {
                    color: #f44336;
                    text-align: center;
                    border: 1px dashed #f44336;
                    margin: 10px 0;
                    padding: 5px;
                }
                .items {
                    margin: 15px 0;
                }
                .total {
                    border-top: 1px dashed #000;
                    margin-top: 10px;
                    padding-top: 10px;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>${companyName}</h2>
                <p>${companyAddress}</p>
            </div>
            
            <div class="receipt-number">
                Receipt #: ${sale.receipt_number}
            </div>
            <div>Date: ${date.toLocaleString()}</div>
            
            ${!isOnline ? '<div class="offline-notice">OFFLINE RECEIPT</div>' : ''}
            
            <div class="items">
                ${sale.items.map(item => `
                    <div>
                        ${item.name} x${item.quantity}
                        <span style="float:right">$${item.price.toFixed(2)}</span>
                    </div>
                `).join('')}
            </div>
            
            <div class="total">
                <div>Subtotal: $${sale.subtotal.toFixed(2)}</div>
                <div>Tax: $${sale.tax.toFixed(2)}</div>
                <div><strong>Total: $${sale.total.toFixed(2)}</strong></div>
            </div>
            
            <div>Payment Method: ${sale.payment_method}</div>
            
            ${sale.change_given ? `
                <div>
                    Amount Paid: $${sale.amount_paid.toFixed(2)}<br>
                    Change: $${sale.change_given.toFixed(2)}
                </div>
            ` : ''}
            
            <div class="footer">
                <p>Thank you for your business!</p>
                ${!isOnline ? '<p>This receipt will be synchronized when online.</p>' : ''}
            </div>
        </body>
        </html>
    `;
}

// Dashboard State
let currentPeriod = 'today';
let currentBranch = 'all';
let revenueChart = null;
let ordersChart = null;
let currentPage = 1;
const itemsPerPage = 10;

document.addEventListener('DOMContentLoaded', function() {
    initializeFilters();
    initializeCharts();
    loadDashboardData();
    initializeWebSocket();
});

function initializeFilters() {
    // Period filters
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentPeriod = this.dataset.period;
            loadDashboardData();
        });
    });

    // Branch filters
    document.querySelectorAll('.branch-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.branch-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentBranch = this.dataset.branch;
            loadDashboardData();
        });
    });

    // Custom date filter
    document.getElementById('apply-custom-date').addEventListener('click', function() {
        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;
        if (startDate && endDate) {
            loadCustomDateData(startDate, endDate);
        }
    });

    // Chart tabs
    document.querySelectorAll('.chart-tab').forEach(btn => {
        btn.addEventListener('click', function() {
            const parent = this.closest('.chart-header, .table-header');
            parent.querySelectorAll('.chart-tab').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            const chartType = this.dataset.chart;
            const period = this.dataset.period;
            const table = this.dataset.table;
            
            if (chartType) {
                loadChartData(chartType, period);
            }
            if (table) {
                loadTableData(period);
            }
        });
    });

    // Pagination
    document.getElementById('prev-page').addEventListener('click', () => changePage(-1));
    document.getElementById('next-page').addEventListener('click', () => changePage(1));
}

// Initialize Charts
function initializeCharts() {
    const revenueCtx = document.getElementById('revenue-chart').getContext('2d');
    const ordersCtx = document.getElementById('orders-chart').getContext('2d');

    // Revenue Chart
    revenueChart = new Chart(revenueCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Income',
                data: [],
                borderColor: '#1a1a1a',
                backgroundColor: 'rgba(26, 26, 26, 0.1)',
                tension: 0.4,
                fill: true
            }, {
                label: 'Expenses',
                data: [],
                borderColor: '#ff6b6b',
                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toLocaleString();
                        }
                    }
                }
            }
        }
    });

    // Orders Chart
    ordersChart = new Chart(ordersCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Orders',
                data: [],
                backgroundColor: ['#1a1a1a', '#d0d0d0', '#6b5ce7'],
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Load Dashboard Data
function loadDashboardData() {
    const params = new URLSearchParams({
        period: currentPeriod,
        branch: currentBranch
    });

    fetch(`/api/dashboard-stats/?${params}`)
        .then(response => response.json())
        .then(data => {
            updateStatsCards(data.stats);
            updateCharts(data.charts);
            updateOrdersTable(data.orders);
        })
        .catch(error => console.error('Error loading dashboard data:', error));
}

// Load Custom Date Data
function loadCustomDateData(startDate, endDate) {
    const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        branch: currentBranch
    });

    fetch(`/api/dashboard-stats/?${params}`)
        .then(response => response.json())
        .then(data => {
            updateStatsCards(data.stats);
            updateCharts(data.charts);
            updateOrdersTable(data.orders);
        })
        .catch(error => console.error('Error loading custom date data:', error));
}

// Update Stats Cards
function updateStatsCards(stats) {
    document.getElementById('total-menus').textContent = stats.total_menus || 0;
    document.getElementById('total-orders').textContent = stats.total_orders || 0;
    document.getElementById('total-clients').textContent = stats.total_clients || 0;
    document.getElementById('revenue-ratio').textContent = '$' + (stats.revenue_ratio || 0).toLocaleString();

    // Update progress bars
    if (stats.orders_percentage) {
        document.getElementById('orders-progress').style.width = stats.orders_percentage + '%';
        document.getElementById('orders-percentage').textContent = stats.orders_percentage + '%';
    }
    if (stats.clients_percentage) {
        document.getElementById('clients-progress').style.width = stats.clients_percentage + '%';
        document.getElementById('clients-percentage').textContent = stats.clients_percentage + '%';
    }
    if (stats.revenue_percentage) {
        document.getElementById('revenue-progress').style.width = stats.revenue_percentage + '%';
        document.getElementById('revenue-percentage').textContent = stats.revenue_percentage + '%';
    }
}

// Update Charts
function updateCharts(chartsData) {
    // Update Revenue Chart
    if (chartsData.revenue) {
        revenueChart.data.labels = chartsData.revenue.labels;
        revenueChart.data.datasets[0].data = chartsData.revenue.income;
        revenueChart.data.datasets[1].data = chartsData.revenue.expenses;
        revenueChart.update();
    }

    // Update Orders Chart
    if (chartsData.orders) {
        ordersChart.data.labels = chartsData.orders.labels;
        ordersChart.data.datasets[0].data = chartsData.orders.data;
        ordersChart.update();
    }
}

// Load Chart Data
function loadChartData(chartType, period) {
    const params = new URLSearchParams({
        chart_type: chartType,
        period: period,
        branch: currentBranch
    });

    fetch(`/api/chart-data/?${params}`)
        .then(response => response.json())
        .then(data => {
            if (chartType === 'revenue') {
                revenueChart.data.labels = data.labels;
                revenueChart.data.datasets[0].data = data.income;
                revenueChart.data.datasets[1].data = data.expenses;
                revenueChart.update();
            } else if (chartType === 'orders') {
                ordersChart.data.labels = data.labels;
                ordersChart.data.datasets[0].data = data.data;
                ordersChart.update();
            }
        })
        .catch(error => console.error('Error loading chart data:', error));
}

// Update Orders Table
function updateOrdersTable(orders) {
    const tbody = document.getElementById('orders-tbody');
    tbody.innerHTML = '';

    if (!orders || orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem;">No orders found</td></tr>';
        return;
    }

    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const paginatedOrders = orders.slice(start, end);

    paginatedOrders.forEach((order, index) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${start + index + 1}</td>
            <td><strong>#${order.receipt_number}</strong></td>
            <td>${formatDate(order.date)}</td>
            <td>${order.cashier_name || 'N/A'}</td>
            <td>${order.branch_name || 'N/A'}</td>
            <td><strong>${parseFloat(order.total_amount).toFixed(2)}</strong></td>
            <td><span class="status-badge ${getStatusClass(order.status)}">${order.status_display}</span></td>
            <td><button class="action-btn" onclick="viewOrder('${order.id}')">⋯</button></td>
        `;
        tbody.appendChild(row);
    });

    updatePagination(orders.length);
}

// Load Table Data
function loadTableData(period) {
    const params = new URLSearchParams({
        period: period,
        branch: currentBranch,
        page: currentPage,
        per_page: itemsPerPage
    });

    fetch(`/api/orders-list/?${params}`)
        .then(response => response.json())
        .then(data => {
            updateOrdersTable(data.orders);
        })
        .catch(error => console.error('Error loading table data:', error));
}

// Pagination
function changePage(direction) {
    currentPage += direction;
    loadDashboardData();
}

function updatePagination(totalItems) {
    const totalPages = Math.ceil(totalItems / itemsPerPage);
    document.getElementById('page-info').textContent = `Page ${currentPage} of ${totalPages}`;
    document.getElementById('prev-page').disabled = currentPage === 1;
    document.getElementById('next-page').disabled = currentPage === totalPages;
}

// Utility Functions
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

function getStatusClass(status) {
    const statusMap = {
        'new': 'status-new',
        'delivery': 'status-delivery',
        'completed': 'status-completed'
    };
    return statusMap[status] || 'status-new';
}

function viewOrder(orderId) {
    window.location.href = `/orders/${orderId}/`;
}

// WebSocket for Real-time Updates
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(protocol + '//' + window.location.host + '/ws/sales/');

    socket.onopen = function() {
        console.log('WebSocket connection established');
    };

    socket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };

    socket.onmessage = function(e) {
        const message = JSON.parse(e.data);
        console.log('WebSocket data received:', message);
        
        // Refresh dashboard data when new sale is made
        if (message.type === 'sales_update') {
            // Force view to today and reload
            currentPeriod = 'today';
            // Toggle active buttons in UI if present
            document.querySelectorAll('.filter-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.period === 'today');
            });
            loadDashboardData();
        }
    };

    socket.onclose = function() {
        console.log('WebSocket connection closed. Attempting to reconnect...');
        setTimeout(initializeWebSocket, 3000);
    };
}
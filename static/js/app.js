/* PCAPdroid Analyzer - Frontend Application */

// State
let charts = {};
let currentPage = 'dashboard';
let appPage = 1;
let domainPage = 1;
let dnsPage = 1;
let searchPage = 1;

// Navigation
function navigateTo(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) pageEl.classList.add('active');

    const navEl = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (navEl) navEl.classList.add('active');

    currentPage = page;

    // Load page data
    switch (page) {
        case 'dashboard': loadDashboard(); break;
        case 'overnight': initOvernightPage(); break;
        case 'apps': loadApps(); break;
        case 'domains': loadDomains(); break;
        case 'dns': loadDNS(); break;
        case 'privacy': loadPrivacy(); break;
        case 'timeline': loadTimeline(); break;
        case 'search': break;
        case 'import': loadImportStatus(); break;
        case 'imports': loadSessions(); break;
        case 'settings': initSettingsPage(); break;
    }
}

// Utility functions
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function truncate(str, len = 30) {
    if (!str) return '-';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

async function apiGet(url, params = {}) {
    const query = new URLSearchParams(params).toString();
    const fullUrl = query ? `${url}?${query}` : url;
    const resp = await fetch(fullUrl);
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
}

// Destroy chart if exists
function destroyChart(id) {
    if (charts[id]) {
        charts[id].destroy();
        delete charts[id];
    }
}

// Chart defaults
Chart.defaults.color = '#9ca3af';
Chart.defaults.borderColor = '#2d3348';
Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif';

// ==================== IMPORT ====================

async function loadImportStatus() {
    try {
        const data = await apiGet('/api/import/status');
        document.getElementById('record-count').textContent = `${data.total_records.toLocaleString()} records loaded`;

        const historyEl = document.getElementById('import-history');
        if (data.imports.length === 0) {
            historyEl.innerHTML = '<p class="text-muted">No imports yet.</p>';
            return;
        }

        let html = '<div class="table-container"><table><thead><tr>' +
            '<th>File</th><th>Rows</th><th>Imported</th><th>Size</th></tr></thead><tbody>';
        data.imports.forEach(imp => {
            html += `<tr>
                <td>${escapeHtml(imp.filename)}</td>
                <td>${imp.row_count?.toLocaleString() || '-'}</td>
                <td>${imp.imported_at}</td>
                <td>${formatBytes(imp.file_size_bytes || 0)}</td>
            </tr>`;
        });
        html += '</tbody></table></div>';
        historyEl.innerHTML = html;
    } catch (e) {
        console.error('Failed to load import status:', e);
    }
}

// File upload
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');

if (uploadArea) {
    uploadArea.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });
}

async function handleFiles(files) {
    for (const file of files) {
        await uploadFile(file);
    }
    loadImportStatus();
}

async function uploadFile(file) {
    const progressEl = document.getElementById('upload-progress');
    const statusEl = document.getElementById('upload-status');
    const percentEl = document.getElementById('upload-percent');
    const barEl = document.getElementById('progress-bar');
    const resultEl = document.getElementById('upload-result');

    progressEl.style.display = 'block';
    statusEl.textContent = `Uploading ${file.name}...`;
    percentEl.textContent = '0%';
    barEl.style.width = '0%';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/import/csv', {
            method: 'POST',
            body: formData,
        });

        const data = await resp.json();

        if (!resp.ok) {
            statusEl.textContent = `Error: ${data.detail || 'Upload failed'}`;
            percentEl.textContent = '✗';
            barEl.style.width = '0%';
            barEl.style.background = 'var(--danger)';
            return;
        }

        barEl.style.width = '100%';
        barEl.style.background = 'var(--success)';
        statusEl.textContent = `Imported ${data.valid_rows.toLocaleString()} records from ${file.name}`;
        percentEl.textContent = '✓';

        if (data.duplicate_rows > 0) {
            statusEl.textContent += ` (${data.duplicate_rows} duplicates skipped)`;
        }

        let resultHtml = `<div class="alert alert-success mt-1">
            <strong>${file.name}</strong><br>
            Total rows: ${data.total_rows.toLocaleString()}<br>
            Valid: ${data.valid_rows.toLocaleString()}<br>
            Duplicates: ${data.duplicate_rows.toLocaleString()}<br>
            Malformed: ${data.malformed_rows.toLocaleString()}
        </div>`;

        if (data.errors && data.errors.length > 0) {
            resultHtml += `<div class="alert alert-error mt-1">
                <strong>Errors (${data.errors.length}):</strong><br>`;
            data.errors.slice(0, 5).forEach(err => {
                resultHtml += escapeHtml(err) + '<br>';
            });
            if (data.errors.length > 5) {
                resultHtml += `... and ${data.errors.length - 5} more`;
            }
            resultHtml += '</div>';
        }

        resultEl.innerHTML = resultHtml;
    } catch (e) {
        statusEl.textContent = `Error: ${e.message}`;
        percentEl.textContent = '✗';
        barEl.style.width = '0%';
        barEl.style.background = 'var(--danger)';
    }
}

// ==================== DASHBOARD ====================

async function loadDashboard() {
    try {
        const data = await apiGet('/api/dashboard/stats');

        // Stats cards
        const statsEl = document.getElementById('dashboard-stats');
        statsEl.innerHTML = `
            <div class="stat-card">
                <div class="stat-label">Total Sent</div>
                <div class="stat-value">${formatBytes(data.total_bytes_sent)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Received</div>
                <div class="stat-value">${formatBytes(data.total_bytes_received)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Traffic</div>
                <div class="stat-value">${formatBytes(data.total_bytes)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Connections</div>
                <div class="stat-value">${data.total_connections.toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Unique Apps</div>
                <div class="stat-value">${data.unique_apps}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Unique Destinations</div>
                <div class="stat-value">${data.unique_destinations}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Recording Start</div>
                <div class="stat-value" style="font-size: 16px;">${data.earliest || 'N/A'}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Recording End</div>
                <div class="stat-value" style="font-size: 16px;">${data.latest || 'N/A'}</div>
            </div>
        `;

        // Charts
        loadDashboardCharts(data);
    } catch (e) {
        console.error('Failed to load dashboard:', e);
    }
}

function loadDashboardCharts(data) {
    // Traffic over time
    destroyChart('traffic-time');
    const timeCtx = document.getElementById('chart-traffic-time').getContext('2d');
    const timeLabels = data.traffic_over_time.map(d => d.hour);
    charts['traffic-time'] = new Chart(timeCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'Sent',
                    data: data.traffic_over_time.map(d => d.bytes_sent),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                },
                {
                    label: 'Received',
                    data: data.traffic_over_time.map(d => d.bytes_received),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 12, maxRotation: 0 } },
                y: { beginAtZero: true, ticks: { callback: v => formatBytes(v) } }
            }
        }
    });

    // Traffic by app (horizontal bar)
    destroyChart('traffic-app');
    const appCtx = document.getElementById('chart-traffic-app').getContext('2d');
    const appData = data.traffic_by_app.slice(0, 10);
    charts['traffic-app'] = new Chart(appCtx, {
        type: 'bar',
        data: {
            labels: appData.map(d => d.app),
            datasets: [{
                label: 'Total Traffic',
                data: appData.map(d => d.bytes_sent + d.bytes_received),
                backgroundColor: 'rgba(59, 130, 246, 0.7)',
                borderColor: '#3b82f6',
                borderWidth: 1,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { beginAtZero: true, ticks: { callback: v => formatBytes(v) } },
                y: { ticks: { autoSkip: false, maxRotation: 45 } }
            }
        }
    });

    // Connections by app
    destroyChart('connections-app');
    const connCtx = document.getElementById('chart-connections-app').getContext('2d');
    const connData = data.connections_by_app.slice(0, 10);
    charts['connections-app'] = new Chart(connCtx, {
        type: 'bar',
        data: {
            labels: connData.map(d => d.app),
            datasets: [{
                label: 'Connections',
                data: connData.map(d => d.connections),
                backgroundColor: 'rgba(139, 92, 246, 0.7)',
                borderColor: '#8b5cf6',
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxRotation: 45 } },
                y: { beginAtZero: true }
            }
        }
    });

    // Traffic by protocol (doughnut)
    destroyChart('traffic-protocol');
    const protoCtx = document.getElementById('chart-traffic-protocol').getContext('2d');
    charts['traffic-protocol'] = new Chart(protoCtx, {
        type: 'doughnut',
        data: {
            labels: data.traffic_by_protocol.map(d => d.protocol),
            datasets: [{
                data: data.traffic_by_protocol.map(d => d.bytes_sent + d.bytes_received),
                backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'],
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right' }
            }
        }
    });
}

// ==================== APPS ====================

async function loadApps() {
    const sortBy = document.getElementById('app-sort').value;
    const order = document.getElementById('app-order').value;

    try {
        const data = await apiGet('/api/apps/list', { sort_by: sortBy, order, page: appPage });

        const tbody = document.getElementById('apps-table-body');
        tbody.innerHTML = data.apps.map(app => `
            <tr>
                <td class="clickable" onclick="showAppDetail('${escapeHtml(app.app_name)}', '${escapeHtml(app.package_name || '')}')">${escapeHtml(app.app_name)}</td>
                <td class="text-muted">${escapeHtml(app.package_name)}</td>
                <td>${formatBytes(app.total_bytes_sent)}</td>
                <td>${formatBytes(app.total_bytes_received)}</td>
                <td><strong>${formatBytes(app.total_bytes_sent + app.total_bytes_received)}</strong></td>
                <td>${app.total_connections.toLocaleString()}</td>
                <td>${app.unique_destinations}</td>
                <td><span class="badge badge-blue">${app.dns_count}</span></td>
            </tr>
        `).join('');

        renderPagination('apps-pagination', data.page, data.total_pages, (p) => { appPage = p; loadApps(); });
    } catch (e) {
        console.error('Failed to load apps:', e);
    }
}

async function showAppDetail(appName, packageName) {
    document.getElementById('apps-list-view').style.display = 'none';
    const detailView = document.getElementById('apps-detail-view');
    detailView.style.display = 'block';

    try {
        const data = await apiGet('/api/apps/details', { app: appName, package: packageName });

        detailView.innerHTML = `
            <a class="back-link" onclick="hideAppDetail()">&larr; Back to apps list</a>
            <div class="detail-header">
                <h2 class="detail-title">${escapeHtml(data.app_name)}</h2>
            </div>
            <div class="detail-meta">
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Package</div>
                    <div class="detail-meta-value" style="font-size: 14px;">${escapeHtml(data.package_name)}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Total Sent</div>
                    <div class="detail-meta-value">${formatBytes(data.total_bytes_sent)}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Total Received</div>
                    <div class="detail-meta-value">${formatBytes(data.total_bytes_received)}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Total Traffic</div>
                    <div class="detail-meta-value">${formatBytes(data.total_bytes)}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Connections</div>
                    <div class="detail-meta-value">${data.total_connections.toLocaleString()}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Destinations</div>
                    <div class="detail-meta-value">${data.unique_destinations}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">DNS Queries</div>
                    <div class="detail-meta-value">${data.dns_count}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">First Seen</div>
                    <div class="detail-meta-value" style="font-size: 14px;">${data.first_seen || 'N/A'}</div>
                </div>
                <div class="detail-meta-item">
                    <div class="detail-meta-label">Last Seen</div>
                    <div class="detail-meta-value" style="font-size: 14px;">${data.last_seen || 'N/A'}</div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Destinations</span>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>IP</th>
                                <th>Domain</th>
                                <th>Port</th>
                                <th>Protocol</th>
                                <th>Connections</th>
                                <th>Sent</th>
                                <th>Received</th>
                                <th>Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.destinations.map(d => `
                                <tr>
                                    <td>${escapeHtml(d.dst_ip)}</td>
                                    <td class="clickable" onclick="showDomainDetail('${escapeHtml(d.domain)}')">${escapeHtml(d.domain)}</td>
                                    <td>${d.dst_port || '-'}</td>
                                    <td><span class="badge badge-green">${d.protocol || '-'}</span></td>
                                    <td>${d.connections.toLocaleString()}</td>
                                    <td>${formatBytes(d.bytes_sent)}</td>
                                    <td>${formatBytes(d.bytes_received)}</td>
                                    <td><strong>${formatBytes(d.bytes_sent + d.bytes_received)}</strong></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="pagination" id="app-detail-pagination"></div>
            </div>
        `;
    } catch (e) {
        detailView.innerHTML = `<div class="alert alert-error">Failed to load app details: ${e.message}</div>
            <a class="back-link" onclick="hideAppDetail()">&larr; Back</a>`;
    }
}

function hideAppDetail() {
    document.getElementById('apps-list-view').style.display = 'block';
    document.getElementById('apps-detail-view').style.display = 'none';
}

function showDomainDetail(domain) {
    navigateTo('domains');
    document.getElementById('domain-search').value = domain;
    loadDomains();
}

// ==================== DOMAINS ====================

async function loadDomains() {
    const search = document.getElementById('domain-search')?.value || '';
    const sortBy = document.getElementById('domain-sort')?.value || 'connections';

    try {
        const data = await apiGet('/api/domains/list', { search, sort_by: sortBy, page: domainPage });

        const tbody = document.getElementById('domains-table-body');
        tbody.innerHTML = data.domains.map(d => `
            <tr>
                <td class="clickable" onclick="showDomainDetail('${escapeHtml(d.domain)}')">${escapeHtml(d.domain)}</td>
                <td class="text-muted">${truncate(escapeHtml(d.apps_contacting), 50)}</td>
                <td>${d.connection_count.toLocaleString()}</td>
                <td>${formatBytes(d.total_bytes_sent)}</td>
                <td>${formatBytes(d.total_bytes_received)}</td>
                <td><strong>${formatBytes(d.total_bytes_sent + d.total_bytes_received)}</strong></td>
            </tr>
        `).join('');

        renderPagination('domains-pagination', data.page, data.total_pages, (p) => { domainPage = p; loadDomains(); });
    } catch (e) {
        console.error('Failed to load domains:', e);
    }
}

// ==================== DNS ====================

async function loadDNS() {
    try {
        const data = await apiGet('/api/dns/analysis', { page: dnsPage });

        const tbody = document.getElementById('dns-table-body');
        tbody.innerHTML = data.dns_domains.map(d => `
            <tr>
                <td class="clickable" onclick="showDomainDetail('${escapeHtml(d.domain)}')">${escapeHtml(d.domain)}</td>
                <td class="text-muted">${truncate(escapeHtml(d.apps), 50)}</td>
                <td>${d.connection_count.toLocaleString()}</td>
                <td>${formatBytes(d.bytes_sent)}</td>
                <td>${formatBytes(d.bytes_received)}</td>
            </tr>
        `).join('');

        renderPagination('dns-pagination', data.page, data.total_pages, (p) => { dnsPage = p; loadDNS(); });

        // DNS mapping
        const mappingEl = document.getElementById('dns-mapping');
        const appMap = {};
        data.app_dns_mapping.forEach(m => {
            if (!appMap[m.app]) appMap[m.app] = [];
            appMap[m.app].push(m);
        });

        let mappingHtml = '<div class="table-container"><table><thead><tr><th>App</th><th>Domain</th><th>Queries</th></tr></thead><tbody>';
        Object.entries(appMap).forEach(([app, domains]) => {
            domains.forEach(d => {
                mappingHtml += `<tr>
                    <td>${escapeHtml(app)}</td>
                    <td>${escapeHtml(d.domain)}</td>
                    <td>${d.queries.toLocaleString()}</td>
                </tr>`;
            });
        });
        mappingHtml += '</tbody></table></div>';
        mappingEl.innerHTML = mappingHtml;
    } catch (e) {
        console.error('Failed to load DNS:', e);
    }
}

// ==================== PRIVACY ====================

async function loadPrivacy() {
    try {
        const data = await apiGet('/api/privacy/metrics');
        const el = document.getElementById('privacy-metrics');

        let html = '';

        // Apps contacting most domains
        html += `<div class="card">
            <div class="card-header"><span class="card-title">Apps Contacting Most Unique Domains</span></div>
            <div class="table-container"><table>
                <thead><tr><th>App</th><th>Unique Domains</th><th>Unique IPs</th><th>Sent</th><th>Received</th></tr></thead>
                <tbody>${data.apps_most_domains.map(d => `
                    <tr>
                        <td class="clickable" onclick="showAppDetail('${escapeHtml(d.app)}', '')">${escapeHtml(d.app)}</td>
                        <td>${d.unique_domains}</td>
                        <td>${d.unique_ips}</td>
                        <td>${formatBytes(d.bytes_sent)}</td>
                        <td>${formatBytes(d.bytes_received)}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
        </div>`;

        // Apps sending most data
        html += `<div class="card">
            <div class="card-header"><span class="card-title">Apps Sending Most Data</span></div>
            <div class="table-container"><table>
                <thead><tr><th>App</th><th>Sent</th><th>Received</th><th>Connections</th></tr></thead>
                <tbody>${data.apps_most_sent.map(d => `
                    <tr>
                        <td class="clickable" onclick="showAppDetail('${escapeHtml(d.app)}', '')">${escapeHtml(d.app)}</td>
                        <td>${formatBytes(d.bytes_sent)}</td>
                        <td>${formatBytes(d.bytes_received)}</td>
                        <td>${d.connections.toLocaleString()}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
        </div>`;

        // Apps receiving most data
        html += `<div class="card">
            <div class="card-header"><span class="card-title">Apps Receiving Most Data</span></div>
            <div class="table-container"><table>
                <thead><tr><th>App</th><th>Sent</th><th>Received</th><th>Connections</th></tr></thead>
                <tbody>${data.apps_most_received.map(d => `
                    <tr>
                        <td class="clickable" onclick="showAppDetail('${escapeHtml(d.app)}', '')">${escapeHtml(d.app)}</td>
                        <td>${formatBytes(d.bytes_sent)}</td>
                        <td>${formatBytes(d.bytes_received)}</td>
                        <td>${d.connections.toLocaleString()}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
        </div>`;

        // Shared domains (contacted by multiple apps)
        html += `<div class="card">
            <div class="card-header"><span class="card-title">Domains Contacted by Multiple Apps</span></div>
            <div class="table-container"><table>
                <thead><tr><th>Domain</th><th>Apps</th><th>Apps List</th></tr></thead>
                <tbody>${data.shared_domains.map(d => `
                    <tr>
                        <td class="clickable" onclick="showDomainDetail('${escapeHtml(d.domain)}')">${escapeHtml(d.domain)}</td>
                        <td><span class="badge badge-yellow">${d.app_count}</span></td>
                        <td class="text-muted">${truncate(escapeHtml(d.apps), 60)}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
        </div>`;

        // Unidentified destinations
        html += `<div class="card">
            <div class="card-header"><span class="card-title">Unidentified Destinations (No Domain Mapped)</span></div>
            <div class="table-container"><table>
                <thead><tr><th>IP Address</th><th>Connections</th><th>Apps</th><th>Sent</th><th>Received</th></tr></thead>
                <tbody>${data.unidentified_destinations.slice(0, 20).map(d => `
                    <tr>
                        <td>${escapeHtml(d.dst_ip)}</td>
                        <td>${d.connection_count.toLocaleString()}</td>
                        <td class="text-muted">${truncate(escapeHtml(d.apps), 50)}</td>
                        <td>${formatBytes(d.bytes_sent)}</td>
                        <td>${formatBytes(d.bytes_received)}</td>
                    </tr>
                `).join('')}</tbody>
            </table></div>
        </div>`;

        el.innerHTML = html;
    } catch (e) {
        console.error('Failed to load privacy metrics:', e);
    }
}

// ==================== TIMELINE ====================

async function loadTimeline() {
    const interval = document.getElementById('timeline-interval').value;
    const app = document.getElementById('timeline-app')?.value || '';
    const domain = document.getElementById('timeline-domain')?.value || '';

    try {
        const data = await apiGet('/api/dashboard/timeline', { interval, app, domain });

        destroyChart('timeline');
        const ctx = document.getElementById('chart-timeline').getContext('2d');
        charts['timeline'] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.data.map(d => d.time_bucket),
                datasets: [
                    {
                        label: 'Sent',
                        data: data.data.map(d => d.bytes_sent),
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    },
                    {
                        label: 'Received',
                        data: data.data.map(d => d.bytes_received),
                        backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top' } },
                scales: {
                    x: { stacked: true, ticks: { maxTicksLimit: 20, maxRotation: 45 } },
                    y: { stacked: true, beginAtZero: true, ticks: { callback: v => formatBytes(v) } }
                }
            }
        });
    } catch (e) {
        console.error('Failed to load timeline:', e);
    }
}

// ==================== SEARCH ====================

async function doSearch() {
    const q = document.getElementById('search-q').value;
    const app = document.getElementById('search-app').value;
    const domain = document.getElementById('search-domain').value;
    const protocol = document.getElementById('search-protocol').value;
    const start = document.getElementById('search-start').value;
    const end = document.getElementById('search-end').value;

    try {
        const data = await apiGet('/api/search/connections', {
            q, app, domain, protocol, start_date: start, end_date: end, page: searchPage
        });

        const tbody = document.getElementById('search-results-body');
        tbody.innerHTML = data.results.map(r => `
            <tr>
                <td class="text-muted" style="white-space: nowrap;">${r.first_seen || '-'}</td>
                <td>${escapeHtml(r.app_name)}</td>
                <td class="text-muted">${escapeHtml(r.package_name)}</td>
                <td><span class="badge badge-green">${r.protocol || '-'}</span></td>
                <td>${escapeHtml(r.dst_ip)}:${r.dst_port || '-'}</td>
                <td>${escapeHtml(r.domain)}</td>
                <td>${formatBytes(r.bytes_sent)}</td>
                <td>${formatBytes(r.bytes_received)}</td>
            </tr>
        `).join('');

        renderPagination('search-pagination', data.page, data.total_pages, (p) => { searchPage = p; doSearch(); });
    } catch (e) {
        console.error('Search failed:', e);
    }
}

// ==================== OVERNIGHT ====================

let onNight = null;          // selected night date (YYYY-MM-DD)
let onAppPage = 1;
let onAppSort = 'traffic';

function pctClass(v) {
    if (v === null || v === undefined) return '';
    return v > 0 ? 'text-warning' : 'text-secondary';
}

function pctText(v) {
    if (v === null || v === undefined) return '-';
    return (v > 0 ? '+' : '') + v.toFixed(0) + '%';
}

async function initOvernightPage() {
    // Load config into inputs once
    try {
        const cfg = await apiGet('/api/overnight/config');
        document.getElementById('on-sleep-start').value = cfg.sleep_start;
        document.getElementById('on-sleep-end').value = cfg.sleep_end;
    } catch (e) { console.error(e); }
    await loadOvernightNights();
}

async function loadOvernightNights() {
    const sel = document.getElementById('on-night-select');
    try {
        const data = await apiGet('/api/overnight/nights', { days: 30 });
        const nights = data.nights.filter(n => n.connection_count > 0);
        if (nights.length === 0) {
            sel.innerHTML = '<option value="">No overnight data</option>';
            document.getElementById('on-summary').innerHTML =
                '<div class="alert alert-info">No overnight traffic found. Import PCAPdroid CSVs first.</div>';
            return;
        }
        sel.innerHTML = nights.map(n =>
            `<option value="${n.night}">${n.night} (${n.connection_count.toLocaleString()} conns)</option>`
        ).join('');
        if (!onNight || !nights.some(n => n.night === onNight)) {
            onNight = nights[0].night;   // most recent night with data
        }
        sel.value = onNight;
        await loadOvernightNight();
    } catch (e) {
        console.error('Failed to load nights:', e);
    }
}

async function loadOvernightNight() {
    onNight = document.getElementById('on-night-select').value;
    if (!onNight) return;
    onAppPage = 1;
    try {
        const data = await apiGet(`/api/overnight/night/${onNight}`);
        renderOvernightSummary(data.summary);
        renderOvernightApps(data.apps, data.baselines);
        renderOvernightBursts(data.bursts);
        renderOvernightInsights(data.insights);
        loadOvernightTimeline();
        loadOvernightComparison();
        document.getElementById('on-app-detail').style.display = 'none';
    } catch (e) {
        console.error('Failed to load night:', e);
    }
}

function renderOvernightSummary(s) {
    const el = document.getElementById('on-summary');
    el.innerHTML = `
        <div class="stat-card"><div class="stat-label">Night</div><div class="stat-value" style="font-size:18px;">${s.night}</div></div>
        <div class="stat-card"><div class="stat-label">Total Traffic</div><div class="stat-value">${formatBytes(s.total_traffic)}</div></div>
        <div class="stat-card"><div class="stat-label">Sent</div><div class="stat-value">${formatBytes(s.bytes_sent)}</div></div>
        <div class="stat-card"><div class="stat-label">Received</div><div class="stat-value">${formatBytes(s.bytes_received)}</div></div>
        <div class="stat-card"><div class="stat-label">Connections</div><div class="stat-value">${s.connections.toLocaleString()}</div></div>
        <div class="stat-card"><div class="stat-label">Unique Apps</div><div class="stat-value">${s.unique_apps}</div></div>
        <div class="stat-card"><div class="stat-label">Unique Destinations</div><div class="stat-value">${s.unique_destinations}</div></div>
        <div class="stat-card"><div class="stat-label">Unique Domains</div><div class="stat-value">${s.unique_domains}</div></div>
        <div class="stat-card"><div class="stat-label">DNS Requests</div><div class="stat-value">${(s.dns_requests || 0).toLocaleString()}</div></div>
        <div class="stat-card"><div class="stat-label">Active Hours</div><div class="stat-value">${s.active_periods}</div></div>
    `;
}

function baselineBadge(b) {
    if (!b || !b.baseline_available) {
        return '<span class="badge" style="background:var(--bg-hover);color:var(--text-muted);">no baseline</span>';
    }
    const color = b.status === 'Higher than baseline' ? 'var(--warning)'
        : b.status === 'Lower than baseline' ? 'var(--accent)' : 'var(--success)';
    return `<span class="badge" style="background:${color};color:#0f1117;">${escapeHtml(b.status)}</span>`;
}

function renderOvernightApps(appsData, baselines) {
    const tbody = document.getElementById('on-apps-body');
    const apps = appsData.apps;
    if (apps.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-muted">No overnight apps for this night.</td></tr>';
        return;
    }
    tbody.innerHTML = apps.map(a => {
        const b = baselines ? baselines[a.app_name] : null;
        return `
        <tr style="cursor:pointer;" onclick="showOvernightApp('${escapeHtml(a.app_name).replace(/'/g, "\\'")}')">
            <td><strong>${escapeHtml(a.app_name)}</strong></td>
            <td class="text-muted">${escapeHtml(a.package_name)}</td>
            <td>${formatBytes(a.bytes_sent)}</td>
            <td>${formatBytes(a.bytes_received)}</td>
            <td><strong>${formatBytes(a.total_traffic)}</strong></td>
            <td>${a.connections.toLocaleString()}</td>
            <td>${a.unique_domains}</td>
            <td class="text-muted" style="white-space:nowrap;">${a.first_activity || '-'}</td>
            <td class="text-muted" style="white-space:nowrap;">${a.last_activity || '-'}</td>
            <td>${baselineBadge(b)}</td>
        </tr>`;
    }).join('');
    renderPagination('on-apps-pagination', appsData.page,
        Math.max(1, Math.ceil(appsData.total / appsData.per_page)),
        (p) => { onAppPage = p; loadOvernightAppsPage(); });
}

async function loadOvernightAppsPage() {
    if (!onNight) return;
    try {
        const apps = await apiGet(`/api/overnight/night/${onNight}/apps`,
            { page: onAppPage, per_page: 50, sort: onAppSort });
        renderOvernightApps(apps, null);
    } catch (e) { console.error(e); }
}

function renderOvernightBursts(bursts) {
    const el = document.getElementById('on-bursts');
    if (!bursts || bursts.length === 0) {
        el.innerHTML = '<div class="text-muted">No activity bursts detected for this night.</div>';
        return;
    }
    el.innerHTML = bursts.map(b => `
        <div class="alert alert-info" style="margin-bottom:8px;">
            <strong>${b.start.slice(11, 16)}–${b.end.slice(11, 16)}</strong>
            &nbsp;${escapeHtml(b.app_name)}&nbsp;—
            ${formatBytes(b.traffic)} total,
            ${b.connections} connections,
            ${b.packets.toLocaleString()} packets
            <span class="badge" style="background:var(--bg-hover);color:var(--text-secondary);margin-left:8px;">${escapeHtml(b.label)}</span>
            <span class="text-muted" style="font-size:12px;"> (${b.ratio_to_mean}× its average bucket)</span>
        </div>
    `).join('');
}

function renderOvernightInsights(insights) {
    const el = document.getElementById('on-insights');
    if (!insights || insights.length === 0) {
        el.innerHTML = '<div class="text-muted">No observations for this night.</div>';
        return;
    }
    el.innerHTML = '<ul style="margin-left:20px;">' +
        insights.map(i => `<li>${escapeHtml(i.text)}</li>`).join('') + '</ul>';
}

async function loadOvernightTimeline() {
    if (!onNight) return;
    const bucket = document.getElementById('on-bucket').value;
    try {
        const data = await apiGet(`/api/overnight/night/${onNight}/timeline`, { bucket_minutes: bucket });
        const buckets = data.buckets;
        const labels = buckets.map(b => b.bucket_start.slice(11, 16));
        const maxTraffic = Math.max(...buckets.map(b => b.traffic), 1);

        destroyChart('overnight-timeline');
        const ctx = document.getElementById('chart-overnight-timeline').getContext('2d');
        charts['overnight-timeline'] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Traffic per bucket',
                    data: buckets.map(b => b.traffic),
                    backgroundColor: buckets.map(b =>
                        b.traffic > maxTraffic * 0.5 ? 'rgba(245, 158, 11, 0.8)' : 'rgba(59, 130, 246, 0.6)'),
                }, {
                    label: 'Connections',
                    data: buckets.map(b => b.connections),
                    type: 'line',
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.3,
                    pointRadius: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' },
                    tooltip: {
                        callbacks: {
                            afterBody: (items) => {
                                const b = buckets[items[0].dataIndex];
                                return `Active apps: ${b.active_apps}`;
                            }
                        }
                    }
                },
                scales: {
                    x: { ticks: { maxTicksLimit: 16, maxRotation: 0 } },
                    y: { beginAtZero: true, ticks: { callback: v => formatBytes(v) } },
                    y1: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false } }
                }
            }
        });
    } catch (e) { console.error('Timeline failed:', e); }
}

async function loadOvernightComparison() {
    if (!onNight) return;
    const el = document.getElementById('on-comparison');
    try {
        const nightsResp = await apiGet('/api/overnight/nights', { days: 30 });
        const nightList = nightsResp.nights.filter(n => n.connection_count > 0).map(n => n.night);
        if (nightList.length < 2) {
            el.innerHTML = '<div class="text-muted">Import at least two nights of data to compare them.</div>';
            return;
        }
        const comp = await apiGet('/api/overnight/compare', { nights: nightList.join(',') });
        const avg = comp.average || {};
        let html = `
            <div class="table-container"><table>
            <thead><tr><th>Night</th><th>Total</th><th>Sent</th><th>Received</th><th>Connections</th><th>Apps</th><th>Domains</th><th>vs avg</th></tr></thead>
            <tbody>`;
        for (const n of comp.nights) {
            const vs = n.vs_avg_total_traffic_pct;
            html += `<tr ${n.night === onNight ? 'style="background:var(--accent-light);"' : ''}>
                <td><strong>${n.night}</strong></td>
                <td>${formatBytes(n.total_traffic)}</td>
                <td>${formatBytes(n.bytes_sent)}</td>
                <td>${formatBytes(n.bytes_received)}</td>
                <td>${n.connections.toLocaleString()}</td>
                <td>${n.unique_apps}</td>
                <td>${n.unique_domains}</td>
                <td class="${pctClass(vs)}">${pctText(vs)}</td>
            </tr>`;
        }
        html += `</tbody></table></div>`;
        if (avg.total_traffic) {
            html += `<div class="text-muted" style="margin-top:8px;">
                Average overnight traffic: ${formatBytes(avg.total_traffic)} ·
                Average connections: ${avg.connections.toLocaleString()} ·
                Average apps: ${avg.unique_apps}</div>`;
        }
        el.innerHTML = html;
    } catch (e) {
        console.error('Comparison failed:', e);
        el.innerHTML = '<div class="text-muted">Comparison unavailable.</div>';
    }
}

async function showOvernightApp(appName) {
    if (!onNight) return;
    const detail = document.getElementById('on-app-detail');
    detail.style.display = 'block';
    detail.innerHTML = '<div class="card mt-2"><div class="text-muted">Loading…</div></div>';
    detail.scrollIntoView({ behavior: 'smooth' });
    try {
        const [destResp, baseResp] = await Promise.all([
            apiGet(`/api/overnight/night/${onNight}/apps/${encodeURIComponent(appName)}/destinations`),
            apiGet(`/api/overnight/baseline/${encodeURIComponent(appName)}`),
        ]);
        const dests = destResp.destinations;
        let html = `
        <div class="card mt-2">
            <div class="card-header">
                <span class="card-title">${escapeHtml(appName)} — overnight destinations</span>
                <button class="btn btn-sm" onclick="hideOvernightApp()">Close</button>
            </div>
            <div class="table-container"><table>
                <thead><tr><th>Destination</th><th>Connections</th><th>Sent</th><th>Received</th><th>Total</th><th>First seen</th><th>Last seen</th><th></th></tr></thead>
                <tbody>`;
        for (const d of dests) {
            html += `<tr>
                <td>${escapeHtml(d.destination)}</td>
                <td>${d.connections.toLocaleString()}</td>
                <td>${formatBytes(d.sent)}</td>
                <td>${formatBytes(d.received)}</td>
                <td><strong>${formatBytes(d.total_traffic)}</strong></td>
                <td class="text-muted" style="white-space:nowrap;">${d.first_seen || '-'}</td>
                <td class="text-muted" style="white-space:nowrap;">${d.last_seen || '-'}</td>
                <td><button class="btn btn-sm" onclick="showOvernightAppConnections('${escapeHtml(appName).replace(/'/g, "\\'")}', '${escapeHtml(d.destination).replace(/'/g, "\\'")}')">Connections</button></td>
            </tr>`;
        }
        html += `</tbody></table></div>`;

        if (baseResp.baseline_available) {
            html += `
            <div class="mt-2" style="padding: 12px; background: var(--bg-secondary); border-radius: var(--radius);">
                <strong>Baseline</strong> (from ${baseResp.baseline_nights_used} previous nights, ${escapeHtml(baseResp.baseline_method)}):<br>
                Typical overnight traffic: ${formatBytes(baseResp.typical_range.low)} – ${formatBytes(baseResp.typical_range.high)}
                (median ${formatBytes(baseResp.median)})<br>
                Last night (${baseResp.last_night_date}): ${formatBytes(baseResp.last_night)} —
                <strong>${escapeHtml(baseResp.status)}</strong><br>
                <span class="text-muted" style="font-size:12px;">${escapeHtml(baseResp.note)}</span>
            </div>`;
        } else if (baseResp.message) {
            html += `<div class="text-muted mt-1">${escapeHtml(baseResp.message)}</div>`;
        }
        html += `<div id="on-conn-drilldown" class="mt-2"></div></div>`;
        detail.innerHTML = html;
    } catch (e) {
        console.error('App detail failed:', e);
        detail.innerHTML = `<div class="card mt-2"><div class="alert alert-error">Failed to load app detail: ${escapeHtml(e.message)}</div></div>`;
    }
}

function hideOvernightApp() {
    const detail = document.getElementById('on-app-detail');
    detail.style.display = 'none';
    detail.innerHTML = '';
}

async function showOvernightAppConnections(appName, destination) {
    const target = document.getElementById('on-conn-drilldown');
    if (!target) return;
    target.innerHTML = '<div class="text-muted">Loading connections…</div>';
    try {
        const params = { page: 1, per_page: 50 };
        if (destination) params.destination = destination;
        const data = await apiGet(
            `/api/overnight/night/${onNight}/apps/${encodeURIComponent(appName)}/connections`, params);
        let html = `<h3 class="mb-1" style="font-size:15px;">Raw connections — ${escapeHtml(appName)}${destination ? ' → ' + escapeHtml(destination) : ''}</h3>
        <div class="table-container"><table>
            <thead><tr><th>Timestamp</th><th>Destination IP</th><th>Domain</th><th>Port</th><th>Protocol</th><th>Sent</th><th>Received</th><th>Status</th></tr></thead>
            <tbody>`;
        for (const c of data.connections) {
            html += `<tr>
                <td class="text-muted" style="white-space:nowrap;">${c.first_seen}</td>
                <td>${escapeHtml(c.dst_ip)}</td>
                <td>${escapeHtml(c.domain) || '-'}</td>
                <td>${c.dst_port ?? '-'}</td>
                <td><span class="badge badge-green">${escapeHtml(c.protocol)}</span></td>
                <td>${formatBytes(c.bytes_sent)}</td>
                <td>${formatBytes(c.bytes_received)}</td>
                <td class="text-muted">${escapeHtml(c.status)}</td>
            </tr>`;
        }
        html += '</tbody></table></div>';
        html += `<div class="text-muted" style="margin-top:6px;">${data.total.toLocaleString()} connections total (showing ${data.connections.length})</div>`;
        target.innerHTML = html;
    } catch (e) {
        console.error('Drill-down failed:', e);
        target.innerHTML = `<div class="alert alert-error">Drill-down failed: ${escapeHtml(e.message)}</div>`;
    }
}

async function saveSleepConfig() {
    const start = document.getElementById('on-sleep-start').value || document.getElementById('set-sleep-start').value;
    const end = document.getElementById('on-sleep-end').value || document.getElementById('set-sleep-end').value;
    const statusEl = document.getElementById('on-config-status');
    try {
        const resp = await fetch(`/api/overnight/config?sleep_start=${encodeURIComponent(start)}&sleep_end=${encodeURIComponent(end)}`,
            { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to save');
        if (statusEl) statusEl.textContent = `Sleep window saved: ${data.sleep_start} → ${data.sleep_end}`;
        await loadOvernightNights();
    } catch (e) {
        if (statusEl) statusEl.textContent = `Error: ${e.message}`;
    }
}

// ==================== IMPORTS / SESSIONS ====================

async function loadSessions() {
    const tbody = document.getElementById('sessions-table-body');
    try {
        const data = await apiGet('/api/sessions');
        if (data.sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-muted">No recording sessions yet. Import CSV files to create one.</td></tr>';
            return;
        }
        tbody.innerHTML = data.sessions.map(s => `
            <tr>
                <td>${s.id}</td>
                <td><strong>${escapeHtml(s.filename)}</strong></td>
                <td class="text-muted" style="white-space:nowrap;">${s.imported_at || '-'}</td>
                <td class="text-muted" style="white-space:nowrap;">${s.first_packet || '-'}</td>
                <td class="text-muted" style="white-space:nowrap;">${s.last_packet || '-'}</td>
                <td>${(s.stored_rows || 0).toLocaleString()}</td>
                <td>${s.total_traffic_bytes ? formatBytes(s.total_traffic_bytes) : '-'}</td>
                <td><button class="btn btn-sm btn-danger" onclick="deleteSession(${s.id}, '${escapeHtml(s.filename).replace(/'/g, "\\'")}')">Delete</button></td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load sessions:', e);
        tbody.innerHTML = '<tr><td colspan="8" class="text-muted">Failed to load sessions.</td></tr>';
    }
}

async function deleteSession(id, filename) {
    if (!confirm(`Delete recording session "${filename}" and all of its raw connection rows? This cannot be undone.`)) return;
    try {
        const resp = await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Delete failed');
        await loadSessions();
    } catch (e) {
        alert(`Delete failed: ${e.message}`);
    }
}

// ==================== SETTINGS ====================

async function initSettingsPage() {
    try {
        const cfg = await apiGet('/api/overnight/config');
        document.getElementById('set-sleep-start').value = cfg.sleep_start;
        document.getElementById('set-sleep-end').value = cfg.sleep_end;
    } catch (e) { console.error(e); }
}

async function deleteAllData() {
    if (!confirm('Delete ALL imported data (raw connections and recording sessions)? This cannot be undone.')) return;
    if (!confirm('Are you absolutely sure? Type-confirm by pressing OK to permanently delete everything.')) return;
    try {
        const resp = await fetch('/api/sessions?confirm=' + encodeURIComponent('DELETE ALL'), { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Delete failed');
        alert('All imported data deleted.');
        await loadSessions();
    } catch (e) {
        alert(`Delete failed: ${e.message}`);
    }
}

function exportAnalysis() {
    if (onNight) {
        window.location.href = `/api/sessions/export/analysis?night=${encodeURIComponent(onNight)}`;
        return false;
    }
    return true;  // no night selected: download all-night export
}

// ==================== PAGINATION ====================

function renderPagination(containerId, currentPage, totalPages, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container || totalPages <= 1) {
        if (container) container.innerHTML = '';
        return;
    }

    let html = `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="window._pageCallback(${currentPage - 1})">&laquo;</button>`;

    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);

    if (start > 1) {
        html += `<button class="page-btn" onclick="window._pageCallback(1)">1</button>`;
        if (start > 2) html += `<span class="text-muted">...</span>`;
    }

    for (let i = start; i <= end; i++) {
        html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" onclick="window._pageCallback(${i})">${i}</button>`;
    }

    if (end < totalPages) {
        if (end < totalPages - 1) html += `<span class="text-muted">...</span>`;
        html += `<button class="page-btn" onclick="window._pageCallback(${totalPages})">${totalPages}</button>`;
    }

    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="window._pageCallback(${currentPage + 1})">&raquo;</button>`;

    container.innerHTML = html;

    // Store callback
    window._pageCallback = onPageChange;
}

// ==================== INIT ====================

document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    loadImportStatus();
});

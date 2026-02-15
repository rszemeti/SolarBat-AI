// SolarBat-AI Dashboard JavaScript

// ═══════════════ TAB SWITCHING ═══════════════

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    document.getElementById('tab-' + tabName).classList.add('active');
    
    // Match button by data attribute or position
    const tabMap = { plan: 0, predictions: 1, accuracy: 2, settings: 3 };
    const buttons = document.querySelectorAll('.tab-btn');
    if (tabMap[tabName] !== undefined && buttons[tabMap[tabName]]) {
        buttons[tabMap[tabName]].classList.add('active');
    }
    
    // Chart.js needs a resize kick when containers become visible
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
}


// ═══════════════ PREDICTION CHARTS (TAB 2) ═══════════════

function initPredictionCharts(data) {
    // Solar forecast
    createLineChart('predSolarChart', data.timeLabels, [
        { label: 'Solar Forecast (kW)', data: data.solarValues, color: '#f39c12', fill: true }
    ], 'kW', true);
    
    // Battery SOC forecast
    createLineChart('predSOCChart', data.timeLabels, [
        { label: 'Battery SOC (%)', data: data.socValues, color: '#2ecc71', fill: true }
    ], '%', false, 0, 100);
    
    // Load forecast
    createLineChart('predLoadChart', data.timeLabels, [
        { label: 'Load Forecast (kW)', data: data.loadValues, color: '#9b59b6', fill: true }
    ], 'kW', true);
    
    // Price forecast
    createLineChart('predPriceChart', data.timeLabels, [
        { label: 'Import (p/kWh)', data: data.importPrices, color: '#e74c3c', fill: false },
        { label: 'Export (p/kWh)', data: data.exportPrices, color: '#27ae60', fill: false, dash: [5, 5] }
    ], 'p/kWh', false);
}

function createLineChart(canvasId, labels, datasets, yLabel, beginAtZero, yMin, yMax) {
    const el = document.getElementById(canvasId);
    if (!el) return;
    const ctx = el.getContext('2d');
    
    const chartDatasets = datasets.map(ds => ({
        label: ds.label,
        data: ds.data,
        borderColor: ds.color,
        backgroundColor: ds.fill ? ds.color + '18' : 'transparent',
        borderWidth: 2.5,
        fill: ds.fill || false,
        tension: 0.35,
        pointRadius: 2,
        pointHoverRadius: 5,
        borderDash: ds.dash || []
    }));
    
    const scaleOpts = { title: { display: true, text: yLabel } };
    if (beginAtZero) scaleOpts.beginAtZero = true;
    if (yMin !== undefined) scaleOpts.min = yMin;
    if (yMax !== undefined) scaleOpts.max = yMax;
    
    new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: chartDatasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: datasets.length > 1 },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + ' ' + yLabel;
                        }
                    }
                }
            },
            scales: {
                y: scaleOpts,
                x: { title: { display: true, text: 'Time' } }
            }
        }
    });
}


// ═══════════════ ACCURACY CHARTS (TAB 3) ═══════════════

function initAccuracyCharts(data) {
    // Solar: predicted vs actual
    createBarComparison('accSolarChart', data.dates,
        data.solar_predicted, data.solar_actual,
        'Solar', 'kWh', '#f39c12', '#27ae60');
    
    // Load: predicted vs actual
    createBarComparison('accLoadChart', data.dates,
        data.load_predicted, data.load_actual,
        'Load', 'kWh', '#3498db', '#2c3e50');
    
    // Price: predicted vs actual
    createBarComparison('accPriceChart', data.dates,
        data.price_predicted_avg, data.price_actual_avg,
        'Avg Price', 'p/kWh', '#e74c3c', '#8e44ad');
    
    // Error trend
    createErrorTrendChart(data);
}

function createBarComparison(canvasId, labels, predicted, actual, name, unit, colorP, colorA) {
    const el = document.getElementById(canvasId);
    if (!el) return;
    
    new Chart(el.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Predicted ' + name,
                    data: predicted,
                    backgroundColor: colorP + '70',
                    borderColor: colorP,
                    borderWidth: 2,
                    borderRadius: 3,
                    barPercentage: 0.75,
                    categoryPercentage: 0.7
                },
                {
                    label: 'Actual ' + name,
                    data: actual,
                    backgroundColor: colorA + '70',
                    borderColor: colorA,
                    borderWidth: 2,
                    borderRadius: 3,
                    barPercentage: 0.75,
                    categoryPercentage: 0.7
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + ' ' + unit,
                        afterBody: function(items) {
                            if (items.length >= 2) {
                                const err = items[0].parsed.y - items[1].parsed.y;
                                const pct = items[1].parsed.y !== 0
                                    ? ((err / items[1].parsed.y) * 100).toFixed(1) : 'N/A';
                                return ['', 'Error: ' + err.toFixed(2) + ' ' + unit + ' (' + pct + '%)'];
                            }
                        }
                    }
                }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: unit } },
                x: { title: { display: true, text: 'Date' } }
            }
        }
    });
}

function createErrorTrendChart(data) {
    const el = document.getElementById('accErrorChart');
    if (!el) return;
    
    new Chart(el.getContext('2d'), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [
                {
                    label: 'Solar MAPE %',
                    data: data.solar_mape,
                    borderColor: '#f39c12',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 6
                },
                {
                    label: 'Load MAPE %',
                    data: data.load_mape,
                    borderColor: '#3498db',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 6
                },
                {
                    label: 'Price MAE (p)',
                    data: data.price_mae,
                    borderColor: '#e74c3c',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Error' }, suggestedMax: 30 },
                x: { title: { display: true, text: 'Date' } }
            }
        }
    });
}


// ═══════════════ SETTINGS (TAB 4) ═══════════════

let originalSettings = {};

function initSettings(data) {
    originalSettings = JSON.parse(JSON.stringify(data));
}

function saveSettings() {
    // Collect all setting inputs
    const inputs = document.querySelectorAll('.setting-input');
    const toggles = document.querySelectorAll('.toggle-switch input');
    const payload = {};
    
    inputs.forEach(input => {
        payload[input.dataset.key] = input.value;
    });
    
    toggles.forEach(toggle => {
        payload[toggle.dataset.key] = toggle.checked;
    });
    
    // POST to AppDaemon endpoint
    fetch('/api/appdaemon/solar_plan_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(resp => {
        if (resp.ok) {
            showSettingsStatus('✅ Settings saved — takes effect next plan cycle');
        } else {
            showSettingsStatus('❌ Failed to save — check AppDaemon logs');
        }
    })
    .catch(err => {
        showSettingsStatus('❌ Error: ' + err.message);
    });
}

function resetSettings() {
    // Reset all inputs to original values
    const inputs = document.querySelectorAll('.setting-input');
    inputs.forEach(input => {
        const key = input.dataset.key;
        if (originalSettings[key] !== undefined) {
            input.value = originalSettings[key];
        }
    });
    
    const toggles = document.querySelectorAll('.toggle-switch input');
    toggles.forEach(toggle => {
        const key = toggle.dataset.key;
        if (originalSettings[key] !== undefined) {
            toggle.checked = originalSettings[key];
        }
    });
    
    showSettingsStatus('↩️ Reset to saved values');
}

function showSettingsStatus(msg) {
    const el = document.getElementById('settings-status');
    if (el) {
        el.textContent = msg;
        setTimeout(() => { el.textContent = ''; }, 4000);
    }
}

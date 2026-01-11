// SolarBat-AI Plan Visualization Charts

// Chart.js configuration and rendering

function createSOCChart(timeLabels, socValues) {
    const ctx = document.getElementById('socChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: 'State of Charge (%)',
                data: socValues,
                borderColor: '#2ecc71',
                backgroundColor: 'rgba(46, 204, 113, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    title: { display: true, text: 'SOC (%)' }
                },
                x: {
                    title: { display: true, text: 'Time' }
                }
            }
        }
    });
}

function createPriceChart(timeLabels, importPrices, exportPrices) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'Import Price (pay to charge)',
                    data: importPrices,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1
                },
                {
                    label: 'Export Price (earn from discharge)',
                    data: exportPrices,
                    borderColor: '#27ae60',
                    backgroundColor: 'rgba(39, 174, 96, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + 'p/kWh';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    title: { display: true, text: 'Price (p/kWh)' }
                },
                x: {
                    title: { display: true, text: 'Time' }
                }
            }
        }
    });
}

function createSolarChart(timeLabels, solarValues) {
    const ctx = document.getElementById('solarChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: 'Solar Generation (kW)',
                data: solarValues,
                borderColor: '#f39c12',
                backgroundColor: 'rgba(243, 156, 18, 0.2)',
                borderWidth: 3,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y.toFixed(2) + ' kW';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Power (kW)' }
                },
                x: {
                    title: { display: true, text: 'Time' }
                }
            }
        }
    });
}

// Initialize all charts when page loads
function initializeCharts(chartData) {
    createSOCChart(chartData.timeLabels, chartData.socValues);
    createPriceChart(chartData.timeLabels, chartData.importPrices, chartData.exportPrices);
    createSolarChart(chartData.timeLabels, chartData.solarValues);
}

/**
 * Admin Dashboard Charts Module
 * - Chart.js integration
 * - Chart configuration
 * - Data fetching and updates
 * - Responsive chart handling
 */

// =============================================================================
// Chart Manager
// =============================================================================
const AdminCharts = {
    instances: new Map(),
    defaultColors: {
        primary: '#667eea',
        secondary: '#764ba2',
        success: '#22c55e',
        warning: '#f59e0b',
        danger: '#ef4444',
        info: '#3b82f6',
        purple: '#8b5cf6',
        cyan: '#0891b2',
        gray: '#64748b'
    },
    gradients: {}
};

// =============================================================================
// Initialization
// =============================================================================
AdminCharts.init = function() {
    // Check if Chart.js is loaded
    if (typeof Chart === 'undefined') {
        console.warn('[AdminCharts] Chart.js not loaded');
        return;
    }

    // Set global Chart.js defaults
    this.setGlobalDefaults();

    // Listen for theme changes
    AdminCore.on('themeChange', () => this.updateChartsTheme());

    // Listen for tab changes
    AdminCore.on('tabChange', (e) => {
        if (e.detail.tabName === 'dashboard' || e.detail.tabName === 'performance-metrics') {
            setTimeout(() => this.resizeAllCharts(), 100);
        }
    });

    // Window resize handling
    window.addEventListener('resize', AdminCore.debounce(() => {
        this.resizeAllCharts();
    }, 250));

    console.log('[AdminCharts] Initialized');
};

// =============================================================================
// Global Chart.js Configuration
// =============================================================================
AdminCharts.setGlobalDefaults = function() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    Chart.defaults.font.family = "'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = isDark ? '#94a3b8' : '#64748b';
    Chart.defaults.borderColor = isDark ? '#334155' : '#e2e8f0';

    // Animation defaults
    Chart.defaults.animation.duration = 750;
    Chart.defaults.animation.easing = 'easeOutQuart';

    // Interaction defaults
    Chart.defaults.interaction.mode = 'index';
    Chart.defaults.interaction.intersect = false;

    // Plugin defaults
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.backgroundColor = isDark ? '#1e293b' : '#ffffff';
    Chart.defaults.plugins.tooltip.titleColor = isDark ? '#f1f5f9' : '#1e293b';
    Chart.defaults.plugins.tooltip.bodyColor = isDark ? '#94a3b8' : '#64748b';
    Chart.defaults.plugins.tooltip.borderColor = isDark ? '#334155' : '#e2e8f0';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.displayColors = true;
    Chart.defaults.plugins.tooltip.boxPadding = 4;
};

// =============================================================================
// Chart Creation
// =============================================================================
AdminCharts.create = function(canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn(`[AdminCharts] Canvas not found: ${canvasId}`);
        return null;
    }

    // Destroy existing chart if any
    this.destroy(canvasId);

    const ctx = canvas.getContext('2d');

    // Create gradients if needed
    if (config.useGradient) {
        this.createGradients(ctx, canvas);
    }

    // Merge with default config
    const mergedConfig = this.mergeConfig(config);

    // Create chart
    const chart = new Chart(ctx, mergedConfig);
    this.instances.set(canvasId, chart);

    return chart;
};

AdminCharts.mergeConfig = function(config) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    const defaultConfig = {
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: true
                }
            },
            scales: {}
        }
    };

    // Deep merge
    return this.deepMerge(defaultConfig, config);
};

AdminCharts.deepMerge = function(target, source) {
    const result = { ...target };

    for (const key of Object.keys(source)) {
        if (source[key] instanceof Object && key in target) {
            result[key] = this.deepMerge(target[key], source[key]);
        } else {
            result[key] = source[key];
        }
    }

    return result;
};

// =============================================================================
// Gradient Helpers
// =============================================================================
AdminCharts.createGradients = function(ctx, canvas) {
    const height = canvas.height || 300;

    // Primary gradient
    const primaryGradient = ctx.createLinearGradient(0, 0, 0, height);
    primaryGradient.addColorStop(0, 'rgba(102, 126, 234, 0.3)');
    primaryGradient.addColorStop(1, 'rgba(102, 126, 234, 0.02)');
    this.gradients.primary = primaryGradient;

    // Success gradient
    const successGradient = ctx.createLinearGradient(0, 0, 0, height);
    successGradient.addColorStop(0, 'rgba(34, 197, 94, 0.3)');
    successGradient.addColorStop(1, 'rgba(34, 197, 94, 0.02)');
    this.gradients.success = successGradient;

    // Info gradient
    const infoGradient = ctx.createLinearGradient(0, 0, 0, height);
    infoGradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
    infoGradient.addColorStop(1, 'rgba(59, 130, 246, 0.02)');
    this.gradients.info = infoGradient;
};

// =============================================================================
// Predefined Chart Types
// =============================================================================
AdminCharts.createLineChart = function(canvasId, data, options = {}) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    return this.create(canvasId, {
        type: 'line',
        useGradient: true,
        data: {
            labels: data.labels || [],
            datasets: data.datasets.map((dataset, index) => ({
                label: dataset.label || `Dataset ${index + 1}`,
                data: dataset.data || [],
                borderColor: dataset.color || this.defaultColors.primary,
                backgroundColor: dataset.fill ? this.gradients.primary : 'transparent',
                borderWidth: 2,
                fill: dataset.fill !== false,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: dataset.color || this.defaultColors.primary,
                pointHoverBorderColor: isDark ? '#1e293b' : '#ffffff',
                pointHoverBorderWidth: 2,
                ...dataset
            }))
        },
        options: {
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxTicksLimit: options.maxXTicks || 8
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: isDark ? 'rgba(51, 65, 85, 0.5)' : 'rgba(226, 232, 240, 0.8)'
                    },
                    ticks: {
                        maxTicksLimit: 5
                    }
                }
            },
            ...options
        }
    });
};

AdminCharts.createBarChart = function(canvasId, data, options = {}) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    return this.create(canvasId, {
        type: 'bar',
        data: {
            labels: data.labels || [],
            datasets: data.datasets.map((dataset, index) => ({
                label: dataset.label || `Dataset ${index + 1}`,
                data: dataset.data || [],
                backgroundColor: dataset.colors || this.defaultColors.primary,
                borderColor: 'transparent',
                borderWidth: 0,
                borderRadius: 6,
                maxBarThickness: options.maxBarThickness || 40,
                ...dataset
            }))
        },
        options: {
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: isDark ? 'rgba(51, 65, 85, 0.5)' : 'rgba(226, 232, 240, 0.8)'
                    },
                    ticks: {
                        maxTicksLimit: 5
                    }
                }
            },
            ...options
        }
    });
};

AdminCharts.createDoughnutChart = function(canvasId, data, options = {}) {
    return this.create(canvasId, {
        type: 'doughnut',
        data: {
            labels: data.labels || [],
            datasets: [{
                data: data.values || [],
                backgroundColor: data.colors || [
                    this.defaultColors.primary,
                    this.defaultColors.success,
                    this.defaultColors.warning,
                    this.defaultColors.info,
                    this.defaultColors.purple
                ],
                borderWidth: 0,
                hoverOffset: 8
            }]
        },
        options: {
            cutout: options.cutout || '70%',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const value = context.raw;
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${context.label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            },
            ...options
        }
    });
};

AdminCharts.createAreaChart = function(canvasId, data, options = {}) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    return this.create(canvasId, {
        type: 'line',
        useGradient: true,
        data: {
            labels: data.labels || [],
            datasets: data.datasets.map((dataset, index) => ({
                label: dataset.label || `Dataset ${index + 1}`,
                data: dataset.data || [],
                borderColor: dataset.color || this.defaultColors.info,
                backgroundColor: this.gradients.info || 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 5,
                ...dataset
            }))
        },
        options: {
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: isDark ? 'rgba(51, 65, 85, 0.5)' : 'rgba(226, 232, 240, 0.8)'
                    }
                }
            },
            ...options
        }
    });
};

// =============================================================================
// Chart Updates
// =============================================================================
AdminCharts.update = function(canvasId, data, animate = true) {
    const chart = this.instances.get(canvasId);
    if (!chart) {
        console.warn(`[AdminCharts] Chart not found: ${canvasId}`);
        return;
    }

    // Update labels
    if (data.labels) {
        chart.data.labels = data.labels;
    }

    // Update datasets
    if (data.datasets) {
        data.datasets.forEach((dataset, index) => {
            if (chart.data.datasets[index]) {
                Object.assign(chart.data.datasets[index], dataset);
            }
        });
    }

    // Update single values array (for pie/doughnut)
    if (data.values && chart.data.datasets[0]) {
        chart.data.datasets[0].data = data.values;
    }

    chart.update(animate ? 'active' : 'none');
};

AdminCharts.destroy = function(canvasId) {
    const chart = this.instances.get(canvasId);
    if (chart) {
        chart.destroy();
        this.instances.delete(canvasId);
    }
};

AdminCharts.destroyAll = function() {
    this.instances.forEach((chart, id) => {
        chart.destroy();
    });
    this.instances.clear();
};

AdminCharts.resizeAllCharts = function() {
    this.instances.forEach((chart) => {
        chart.resize();
    });
};

// =============================================================================
// Theme Updates
// =============================================================================
AdminCharts.updateChartsTheme = function() {
    // Update global defaults
    this.setGlobalDefaults();

    // Recreate all charts with new theme
    this.instances.forEach((chart, canvasId) => {
        const config = chart.config;
        this.destroy(canvasId);
        this.create(canvasId, config);
    });
};

// =============================================================================
// Dashboard Charts
// =============================================================================
AdminCharts.initDashboardCharts = async function() {
    try {
        // Fetch data
        const [metricsData, sourceData] = await Promise.all([
            AdminCore.apiCall('/api/admin/metrics/recent?limit=24'),
            AdminCore.apiCall('/api/admin/metrics/source-performance')
        ]);

        // Create search trend chart
        if (metricsData?.searches) {
            this.createSearchTrendChart(metricsData.searches);
        }

        // Create source distribution chart (API returns {local, web, docs} directly)
        if (sourceData?.local || sourceData?.web || sourceData?.docs) {
            this.createSourceDistributionChart(sourceData);
        }

        // Create response time chart
        if (metricsData?.searches) {
            this.createResponseTimeChart(metricsData.searches);
        }

    } catch (error) {
        console.error('[AdminCharts] Failed to load dashboard charts:', error);
    }
};

AdminCharts.createSearchTrendChart = function(searches) {
    // Process data - group by hour
    const hourlyData = {};
    const now = new Date();

    for (let i = 23; i >= 0; i--) {
        const hour = new Date(now.getTime() - i * 3600000);
        const key = hour.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
        hourlyData[key] = 0;
    }

    searches.forEach(search => {
        const date = new Date(search.timestamp);
        const key = date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
        if (hourlyData.hasOwnProperty(key)) {
            hourlyData[key]++;
        }
    });

    const labels = Object.keys(hourlyData);
    const data = Object.values(hourlyData);

    this.createLineChart('searchTrendChart', {
        labels,
        datasets: [{
            label: '검색 수',
            data,
            color: this.defaultColors.primary,
            fill: true
        }]
    }, {
        maxXTicks: 12
    });
};

AdminCharts.createSourceDistributionChart = function(sourcePerformance) {
    const sources = {
        local: { label: '로컬 문서', color: this.defaultColors.gray },
        web: { label: '웹 검색', color: this.defaultColors.info },
        docs: { label: '공식 문서', color: this.defaultColors.warning }
    };

    const labels = [];
    const values = [];
    const colors = [];

    Object.entries(sourcePerformance).forEach(([key, data]) => {
        if (sources[key]) {
            labels.push(sources[key].label);
            values.push(data.count || 0);
            colors.push(sources[key].color);
        }
    });

    this.createDoughnutChart('sourceDistributionChart', {
        labels,
        values,
        colors
    });

    // Update legend
    this.updateDoughnutLegend('sourceDistributionLegend', labels, values, colors);
};

AdminCharts.createResponseTimeChart = function(searches) {
    // Group response times into buckets
    const buckets = {
        '< 1초': 0,
        '1-2초': 0,
        '2-3초': 0,
        '3-5초': 0,
        '> 5초': 0
    };

    searches.forEach(search => {
        const time = search.response_time || 0;
        if (time < 1) buckets['< 1초']++;
        else if (time < 2) buckets['1-2초']++;
        else if (time < 3) buckets['2-3초']++;
        else if (time < 5) buckets['3-5초']++;
        else buckets['> 5초']++;
    });

    const labels = Object.keys(buckets);
    const data = Object.values(buckets);

    this.createBarChart('responseTimeChart', {
        labels,
        datasets: [{
            label: '요청 수',
            data,
            colors: [
                this.defaultColors.success,
                this.defaultColors.info,
                this.defaultColors.warning,
                this.defaultColors.danger,
                this.defaultColors.gray
            ]
        }]
    });
};

AdminCharts.updateDoughnutLegend = function(containerId, labels, values, colors) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const total = values.reduce((a, b) => a + b, 0);

    container.innerHTML = labels.map((label, index) => {
        const value = values[index];
        const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;

        return `
            <div class="chart-doughnut-legend-item">
                <div class="chart-doughnut-legend-left">
                    <span class="chart-legend-color" style="background: ${colors[index]}"></span>
                    <span class="chart-legend-label">${label}</span>
                </div>
                <div class="chart-doughnut-legend-right">
                    <span class="chart-doughnut-legend-value">${AdminCore.formatNumber(value)}</span>
                    <span class="chart-doughnut-legend-percent">(${percentage}%)</span>
                </div>
            </div>
        `;
    }).join('');
};

// =============================================================================
// Period Selector
// =============================================================================
AdminCharts.setPeriod = function(period, chartId) {
    // Update button states
    const buttons = document.querySelectorAll(`[data-chart="${chartId}"] .chart-period-btn`);
    buttons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.period === period);
    });

    // Fetch new data and update chart
    this.loadChartData(chartId, period);
};

AdminCharts.loadChartData = async function(chartId, period) {
    try {
        AdminCore.setLoading(true, `#${chartId}`);

        const periodMap = {
            '24h': 24,
            '7d': 168,
            '30d': 720
        };

        const limit = periodMap[period] || 24;
        const data = await AdminCore.apiCall(`/api/admin/metrics/recent?limit=${limit}`);

        // Update chart based on type
        if (chartId === 'searchTrendChart' && data?.searches) {
            this.createSearchTrendChart(data.searches);
        }

        AdminCore.setLoading(false, `#${chartId}`);
    } catch (error) {
        console.error(`[AdminCharts] Failed to load data for ${chartId}:`, error);
        AdminCore.setLoading(false, `#${chartId}`);
    }
};

// =============================================================================
// Export
// =============================================================================
window.AdminCharts = AdminCharts;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait for Chart.js to be available
    if (typeof Chart !== 'undefined') {
        AdminCharts.init();
    } else {
        console.warn('[AdminCharts] Waiting for Chart.js...');
    }
});

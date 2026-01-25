/**
 * Admin Dashboard Filters Module
 * - Date range picker
 * - Filter management
 * - Search functionality
 * - Export utilities
 */

// =============================================================================
// Filter Manager
// =============================================================================
const AdminFilters = {
    state: {
        dateRange: {
            start: null,
            end: null,
            preset: null
        },
        activeFilters: {},
        searchQuery: ''
    },
    presets: {
        '24h': { label: '24시간', hours: 24 },
        '7d': { label: '7일', days: 7 },
        '30d': { label: '30일', days: 30 },
        'all': { label: '전체', all: true }
    }
};

// =============================================================================
// Initialization
// =============================================================================
AdminFilters.init = function() {
    this.initDatePickers();
    this.initPresetButtons();
    this.initSearchInputs();
    this.initFilterSelects();

    console.log('[AdminFilters] Initialized');
};

// =============================================================================
// Date Range Picker
// =============================================================================
AdminFilters.initDatePickers = function() {
    // Initialize all date inputs
    document.querySelectorAll('input[type="datetime-local"]').forEach(input => {
        // Set max date to now
        const now = new Date();
        const maxDate = this.formatDateTimeLocal(now);
        input.setAttribute('max', maxDate);

        // Set default values based on ID
        if (input.id.includes('start')) {
            const defaultStart = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            input.value = this.formatDateTimeLocal(defaultStart);
        } else if (input.id.includes('end')) {
            input.value = maxDate;
        }

        // Add change listener
        input.addEventListener('change', () => {
            this.handleDateChange(input);
        });
    });
};

AdminFilters.formatDateTimeLocal = function(date) {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
};

AdminFilters.handleDateChange = function(input) {
    const context = input.closest('[data-filter-context]')?.dataset.filterContext || 'global';

    if (input.id.includes('start')) {
        this.state.dateRange.start = new Date(input.value);
    } else if (input.id.includes('end')) {
        this.state.dateRange.end = new Date(input.value);
    }

    // Clear preset selection
    this.state.dateRange.preset = null;
    this.updatePresetButtons(context);

    // Emit filter change
    AdminCore.emit('filterChange', {
        context,
        type: 'dateRange',
        value: { ...this.state.dateRange }
    });
};

// =============================================================================
// Preset Buttons
// =============================================================================
AdminFilters.initPresetButtons = function() {
    document.querySelectorAll('[data-preset]').forEach(button => {
        button.addEventListener('click', () => {
            const preset = button.dataset.preset;
            const context = button.closest('[data-filter-context]')?.dataset.filterContext || 'global';
            this.setPreset(preset, context);
        });
    });
};

AdminFilters.setPreset = function(preset, context = 'global') {
    const presetConfig = this.presets[preset];
    if (!presetConfig) return;

    const now = new Date();
    let start, end;

    if (presetConfig.hours) {
        start = new Date(now.getTime() - presetConfig.hours * 60 * 60 * 1000);
        end = now;
    } else if (presetConfig.days) {
        start = new Date(now.getTime() - presetConfig.days * 24 * 60 * 60 * 1000);
        end = now;
    } else if (presetConfig.all) {
        start = null;
        end = null;
    }

    this.state.dateRange = {
        start,
        end,
        preset
    };

    // Update UI
    this.updatePresetButtons(context);
    this.updateDateInputs(context);

    // Emit filter change
    AdminCore.emit('filterChange', {
        context,
        type: 'dateRange',
        value: { ...this.state.dateRange }
    });
};

AdminFilters.updatePresetButtons = function(context) {
    const container = context === 'global'
        ? document
        : document.querySelector(`[data-filter-context="${context}"]`);

    if (!container) return;

    container.querySelectorAll('[data-preset]').forEach(button => {
        const isActive = button.dataset.preset === this.state.dateRange.preset;
        button.classList.toggle('active', isActive);
        button.classList.toggle('btn-primary', isActive);
        button.classList.toggle('btn-secondary', !isActive);
    });
};

AdminFilters.updateDateInputs = function(context) {
    const container = context === 'global'
        ? document
        : document.querySelector(`[data-filter-context="${context}"]`);

    if (!container) return;

    const startInput = container.querySelector('input[id*="start"]');
    const endInput = container.querySelector('input[id*="end"]');

    if (startInput && this.state.dateRange.start) {
        startInput.value = this.formatDateTimeLocal(this.state.dateRange.start);
    }

    if (endInput && this.state.dateRange.end) {
        endInput.value = this.formatDateTimeLocal(this.state.dateRange.end);
    }
};

// =============================================================================
// Search Inputs
// =============================================================================
AdminFilters.initSearchInputs = function() {
    document.querySelectorAll('.table-search input, .search-input').forEach(input => {
        const debouncedSearch = AdminCore.debounce((value) => {
            this.handleSearch(input, value);
        }, 300);

        input.addEventListener('input', (e) => {
            debouncedSearch(e.target.value);
        });

        // Clear on escape
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                input.value = '';
                this.handleSearch(input, '');
            }
        });
    });
};

AdminFilters.handleSearch = function(input, value) {
    const context = input.closest('[data-filter-context]')?.dataset.filterContext ||
                   input.closest('.tab-content')?.id?.replace('-tab', '') ||
                   'global';

    this.state.searchQuery = value;

    AdminCore.emit('filterChange', {
        context,
        type: 'search',
        value
    });
};

// =============================================================================
// Filter Selects
// =============================================================================
AdminFilters.initFilterSelects = function() {
    document.querySelectorAll('.table-filter-select, select[data-filter]').forEach(select => {
        select.addEventListener('change', (e) => {
            this.handleFilterSelect(select);
        });
    });
};

AdminFilters.handleFilterSelect = function(select) {
    const filterName = select.dataset.filter || select.id;
    const context = select.closest('[data-filter-context]')?.dataset.filterContext ||
                   select.closest('.tab-content')?.id?.replace('-tab', '') ||
                   'global';
    const value = select.value;

    this.state.activeFilters[filterName] = value;

    AdminCore.emit('filterChange', {
        context,
        type: 'select',
        filter: filterName,
        value
    });
};

// =============================================================================
// Filter Reset
// =============================================================================
AdminFilters.reset = function(context = 'global') {
    // Reset state
    this.state.dateRange = {
        start: null,
        end: null,
        preset: null
    };
    this.state.activeFilters = {};
    this.state.searchQuery = '';

    const container = context === 'global'
        ? document
        : document.querySelector(`[data-filter-context="${context}"]`) ||
          document.getElementById(`${context}-tab`);

    if (!container) return;

    // Reset date inputs
    container.querySelectorAll('input[type="datetime-local"]').forEach(input => {
        input.value = '';
    });

    // Reset search inputs
    container.querySelectorAll('.table-search input, .search-input').forEach(input => {
        input.value = '';
    });

    // Reset selects
    container.querySelectorAll('.table-filter-select, select[data-filter]').forEach(select => {
        select.selectedIndex = 0;
    });

    // Reset preset buttons
    container.querySelectorAll('[data-preset]').forEach(button => {
        button.classList.remove('active', 'btn-primary');
        button.classList.add('btn-secondary');
    });

    AdminCore.emit('filterChange', {
        context,
        type: 'reset'
    });
};

// =============================================================================
// Export Utilities
// =============================================================================
AdminFilters.exportToCSV = function(data, filename = 'export.csv') {
    if (!data || !data.length) {
        AdminCore.toast('내보낼 데이터가 없습니다.', 'warning');
        return;
    }

    // Get headers from first row
    const headers = Object.keys(data[0]);

    // Build CSV content
    const csvContent = [
        headers.join(','),
        ...data.map(row =>
            headers.map(header => {
                let cell = row[header];
                if (cell === null || cell === undefined) cell = '';
                // Escape quotes and wrap in quotes if contains comma
                cell = String(cell).replace(/"/g, '""');
                if (cell.includes(',') || cell.includes('\n') || cell.includes('"')) {
                    cell = `"${cell}"`;
                }
                return cell;
            }).join(',')
        )
    ].join('\n');

    // Add BOM for Korean characters
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });

    // Download
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    AdminCore.toast('파일이 다운로드되었습니다.', 'success');
};

AdminFilters.exportToJSON = function(data, filename = 'export.json') {
    if (!data) {
        AdminCore.toast('내보낼 데이터가 없습니다.', 'warning');
        return;
    }

    const jsonContent = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });

    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    AdminCore.toast('파일이 다운로드되었습니다.', 'success');
};

// =============================================================================
// Query String Builder
// =============================================================================
AdminFilters.buildQueryString = function(context = 'global') {
    const params = new URLSearchParams();

    // Add date range
    if (this.state.dateRange.start) {
        params.set('start_date', this.state.dateRange.start.toISOString());
    }
    if (this.state.dateRange.end) {
        params.set('end_date', this.state.dateRange.end.toISOString());
    }

    // Add search query
    if (this.state.searchQuery) {
        params.set('search', this.state.searchQuery);
    }

    // Add active filters
    Object.entries(this.state.activeFilters).forEach(([key, value]) => {
        if (value) {
            params.set(key, value);
        }
    });

    return params.toString();
};

// =============================================================================
// Filter Bar Component
// =============================================================================
AdminFilters.createFilterBar = function(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const {
        showDatePresets = true,
        showDatePickers = true,
        showSearch = true,
        showExport = true,
        showRefresh = true,
        filters = [],
        context = 'global',
        onRefresh = null
    } = options;

    let html = `<div class="filter-bar flex items-center gap-md flex-wrap" data-filter-context="${context}">`;

    // Date presets
    if (showDatePresets) {
        html += `
            <div class="filter-group flex items-center gap-sm">
                <button class="btn btn-sm btn-secondary" data-preset="24h">24시간</button>
                <button class="btn btn-sm btn-secondary" data-preset="7d">7일</button>
                <button class="btn btn-sm btn-secondary" data-preset="30d">30일</button>
            </div>
        `;
    }

    // Date pickers
    if (showDatePickers) {
        html += `
            <div class="filter-group flex items-center gap-sm">
                <input type="datetime-local" id="${context}-start-time" class="form-input" style="width: auto;">
                <span class="text-muted">~</span>
                <input type="datetime-local" id="${context}-end-time" class="form-input" style="width: auto;">
            </div>
        `;
    }

    // Custom filters
    filters.forEach(filter => {
        html += `
            <div class="filter-group">
                <select class="table-filter-select" data-filter="${filter.name}" id="${context}-${filter.name}">
                    <option value="">${filter.placeholder || '전체'}</option>
                    ${filter.options.map(opt =>
                        `<option value="${opt.value}">${opt.label}</option>`
                    ).join('')}
                </select>
            </div>
        `;
    });

    // Search
    if (showSearch) {
        html += `
            <div class="filter-group table-search" style="margin-left: auto;">
                <span class="table-search-icon">🔍</span>
                <input type="text" placeholder="검색..." class="search-input">
            </div>
        `;
    }

    // Actions
    html += '<div class="filter-actions flex items-center gap-sm">';

    if (showExport) {
        html += `<button class="btn btn-sm btn-secondary" onclick="AdminFilters.handleExport('${context}')">📥 내보내기</button>`;
    }

    if (showRefresh) {
        html += `<button class="btn btn-sm btn-primary" onclick="AdminFilters.handleRefresh('${context}')">🔄 새로고침</button>`;
    }

    html += '</div></div>';

    container.innerHTML = html;

    // Re-initialize inputs
    this.initDatePickers();
    this.initPresetButtons();
    this.initSearchInputs();
    this.initFilterSelects();

    // Store refresh handler
    if (onRefresh) {
        this.refreshHandlers = this.refreshHandlers || {};
        this.refreshHandlers[context] = onRefresh;
    }
};

AdminFilters.handleExport = function(context) {
    AdminCore.emit('exportRequest', { context });
};

AdminFilters.handleRefresh = function(context) {
    if (this.refreshHandlers?.[context]) {
        this.refreshHandlers[context]();
    } else {
        AdminCore.emit('refreshRequest', { context });
    }
};

// =============================================================================
// Export
// =============================================================================
window.AdminFilters = AdminFilters;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    AdminFilters.init();
});

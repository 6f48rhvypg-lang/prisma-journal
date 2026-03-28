// Journal App - shared JavaScript utilities

/**
 * Dark mode toggle with localStorage persistence.
 */
(function initTheme() {
    const toggle = document.getElementById('theme-toggle');
    const lightIcon = document.getElementById('theme-light-icon');
    const darkIcon = document.getElementById('theme-dark-icon');
    const logoLight = document.getElementById('logo-light');
    const logoDark = document.getElementById('logo-dark');

    function updateIcons() {
        const isDark = document.documentElement.classList.contains('dark');
        if (lightIcon) lightIcon.classList.toggle('hidden', !isDark);
        if (darkIcon) darkIcon.classList.toggle('hidden', isDark);
        if (logoLight) logoLight.classList.toggle('hidden', isDark);
        if (logoDark) logoDark.classList.toggle('hidden', !isDark);
    }

    updateIcons();

    if (toggle) {
        toggle.addEventListener('click', () => {
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            updateIcons();
        });
    }
})();

/**
 * Sidebar toggle (mobile).
 */
(function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const openBtn = document.getElementById('sidebar-open');
    const closeBtn = document.getElementById('sidebar-close');

    if (!sidebar || !overlay) return;

    function openSidebar() {
        sidebar.classList.remove('-translate-x-full');
        overlay.classList.remove('pointer-events-none');
        overlay.classList.add('opacity-100');
    }

    function closeSidebar() {
        sidebar.classList.add('-translate-x-full');
        overlay.classList.add('pointer-events-none');
        overlay.classList.remove('opacity-100');
    }

    if (openBtn) openBtn.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    overlay.addEventListener('click', closeSidebar);
})();

/**
 * Make a JSON API request.
 */
async function apiRequest(url, method = 'GET', body = null) {
    const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(url, opts);
    return resp.json();
}

/**
 * Format a date string for display.
 */
function formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

/**
 * Debounce a function call.
 */
function debounce(fn, ms = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

// ---------------------------------------------------------------------------
// Toast Notification System
// ---------------------------------------------------------------------------

const Toast = {
    container: null,
    queue: [],
    maxVisible: 3,

    /**
     * Initialize the toast container.
     */
    init() {
        if (this.container) return;

        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        this.container.className = 'fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm';
        document.body.appendChild(this.container);
    },

    /**
     * Show a toast notification.
     * @param {string} message - The message to display
     * @param {string} type - 'success', 'error', 'warning', 'info'
     * @param {number} duration - Auto-dismiss after ms (0 for persistent)
     * @param {object} options - Additional options (action, onClose)
     */
    show(message, type = 'info', duration = 5000, options = {}) {
        this.init();

        const toast = document.createElement('div');
        toast.className = `toast-item transform transition-all duration-300 translate-x-full opacity-0
            flex items-start gap-3 p-4 rounded-lg shadow-lg border
            ${this._getTypeClasses(type)}`;

        const icon = this._getIcon(type);
        const dismissBtn = duration === 0 || options.persistent ? `
            <button class="toast-close ml-auto text-current opacity-60 hover:opacity-100" aria-label="Dismiss">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        ` : '';

        const actionBtn = options.action ? `
            <button class="toast-action text-sm font-medium underline ml-2">${options.action.label}</button>
        ` : '';

        toast.innerHTML = `
            <div class="shrink-0">${icon}</div>
            <div class="flex-1 min-w-0">
                <p class="text-sm font-medium">${this._escapeHtml(message)}</p>
                ${options.details ? `<p class="text-xs opacity-75 mt-1">${this._escapeHtml(options.details)}</p>` : ''}
                ${actionBtn}
            </div>
            ${dismissBtn}
        `;

        this.container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.remove('translate-x-full', 'opacity-0');
        });

        // Set up event listeners
        const closeBtn = toast.querySelector('.toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this._dismiss(toast, options.onClose));
        }

        const actionButton = toast.querySelector('.toast-action');
        if (actionButton && options.action?.onClick) {
            actionButton.addEventListener('click', () => {
                options.action.onClick();
                this._dismiss(toast);
            });
        }

        // Auto-dismiss
        if (duration > 0) {
            setTimeout(() => this._dismiss(toast, options.onClose), duration);
        }

        return toast;
    },

    success(message, options = {}) {
        return this.show(message, 'success', options.duration || 4000, options);
    },

    error(message, options = {}) {
        return this.show(message, 'error', options.duration || 8000, options);
    },

    warning(message, options = {}) {
        return this.show(message, 'warning', options.duration || 6000, options);
    },

    info(message, options = {}) {
        return this.show(message, 'info', options.duration || 5000, options);
    },

    _dismiss(toast, callback) {
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => {
            toast.remove();
            if (callback) callback();
        }, 300);
    },

    _getTypeClasses(type) {
        const classes = {
            success: 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800 text-green-800 dark:text-green-200',
            error: 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-800 dark:text-red-200',
            warning: 'bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200',
            info: 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200',
        };
        return classes[type] || classes.info;
    },

    _getIcon(type) {
        const icons = {
            success: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
            error: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
            warning: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>',
            info: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
        };
        return icons[type] || icons.info;
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// ---------------------------------------------------------------------------
// Error Modal Dialog
// ---------------------------------------------------------------------------

const ErrorModal = {
    modal: null,

    /**
     * Show an error modal for critical errors.
     * @param {object} options - Modal configuration
     */
    show(options = {}) {
        const {
            title = 'Error',
            message = 'An error occurred',
            details = null,
            guidance = null,
            actions = [{ label: 'Dismiss', primary: true }],
            onClose = null,
        } = options;

        // Remove existing modal
        this.hide();

        this.modal = document.createElement('div');
        this.modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4';
        this.modal.innerHTML = `
            <div class="fixed inset-0 bg-black/50 backdrop-blur-sm" data-backdrop></div>
            <div class="relative bg-white dark:bg-surface-800 rounded-2xl shadow-xl max-w-md w-full p-6 transform transition-all scale-95 opacity-0">
                <div class="flex items-start gap-4">
                    <div class="shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                        <svg class="w-5 h-5 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                        </svg>
                    </div>
                    <div class="flex-1">
                        <h3 class="text-lg font-semibold text-surface-900 dark:text-white">${this._escapeHtml(title)}</h3>
                        <p class="mt-2 text-sm text-surface-600 dark:text-surface-300">${this._escapeHtml(message)}</p>
                        ${details ? `<pre class="mt-3 p-2 bg-surface-100 dark:bg-surface-700 rounded text-xs overflow-auto max-h-32">${this._escapeHtml(details)}</pre>` : ''}
                        ${guidance ? `<div class="mt-3 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                            <p class="text-xs font-medium text-amber-800 dark:text-amber-200">Suggestion</p>
                            <p class="text-xs text-amber-700 dark:text-amber-300 mt-1">${this._escapeHtml(guidance)}</p>
                        </div>` : ''}
                    </div>
                </div>
                <div class="mt-6 flex justify-end gap-3" data-actions></div>
            </div>
        `;

        // Add action buttons
        const actionsContainer = this.modal.querySelector('[data-actions]');
        actions.forEach((action, index) => {
            const btn = document.createElement('button');
            btn.className = action.primary
                ? 'px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700'
                : 'px-4 py-2 text-sm font-medium text-surface-700 dark:text-surface-300 bg-surface-100 dark:bg-surface-700 rounded-lg hover:bg-surface-200 dark:hover:bg-surface-600';
            btn.textContent = action.label;
            btn.addEventListener('click', () => {
                if (action.onClick) action.onClick();
                this.hide();
            });
            actionsContainer.appendChild(btn);
        });

        // Close on backdrop click
        this.modal.querySelector('[data-backdrop]').addEventListener('click', () => {
            this.hide();
            if (onClose) onClose();
        });

        document.body.appendChild(this.modal);

        // Animate in
        requestAnimationFrame(() => {
            const content = this.modal.querySelector('.relative');
            content.classList.remove('scale-95', 'opacity-0');
        });
    },

    hide() {
        if (this.modal) {
            this.modal.remove();
            this.modal = null;
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// ---------------------------------------------------------------------------
// Progress Indicator
// ---------------------------------------------------------------------------

const Progress = {
    overlay: null,
    cancelCallback: null,

    /**
     * Show a progress indicator for long-running operations.
     * @param {object} options - Progress configuration
     */
    show(options = {}) {
        const {
            message = 'Processing...',
            cancellable = false,
            onCancel = null,
        } = options;

        this.hide();
        this.cancelCallback = onCancel;

        this.overlay = document.createElement('div');
        this.overlay.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm';
        this.overlay.innerHTML = `
            <div class="surface-panel p-6 max-w-xs w-full text-center">
                <div class="hb-loader mx-auto mb-4">
                    <svg class="hb-heart" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M12 20.5s-7-4.35-9.4-8.2C.6 9.2 2.2 5.5 6 5.5c2.1 0 3.4 1.2 4 2.3.6-1.1 1.9-2.3 4-2.3 3.8 0 5.4 3.7 3.4 6.8C19 16.1 12 20.5 12 20.5z"/>
                    </svg>
                    <svg class="hb-brain" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M8.5 5.5a3 3 0 015.5-1.5 3 3 0 015.5 1.5 3 3 0 010 6 3 3 0 01-1.5 5.6 3 3 0 01-5.5 1.4 3 3 0 01-5.5-1.4A3 3 0 013 11.5a3 3 0 015.5-6z"/>
                    </svg>
                </div>
                <p class="text-sm font-medium text-surface-700" data-message>${this._escapeHtml(message)}</p>
                <div class="mt-2 w-full bg-surface-200 rounded-full h-1.5" data-progress-bar style="display: none;">
                    <div class="bg-surface-900 h-1.5 rounded-full transition-all duration-300" style="width: 0%" data-progress-fill></div>
                </div>
                <p class="text-xs text-surface-500 mt-2" data-elapsed style="display: none;"></p>
                ${cancellable ? `
                    <button class="mt-4 px-4 py-2 text-sm font-medium text-surface-600 hover:text-surface-900" data-cancel>
                        Cancel
                    </button>
                ` : ''}
            </div>
        `;

        if (cancellable) {
            this.overlay.querySelector('[data-cancel]').addEventListener('click', () => {
                if (this.cancelCallback) this.cancelCallback();
                this.hide();
            });
        }

        document.body.appendChild(this.overlay);
        this._startTimer();
    },

    /**
     * Update progress percentage and message.
     */
    update(options = {}) {
        if (!this.overlay) return;

        const { percent, message } = options;

        if (message) {
            const msgEl = this.overlay.querySelector('[data-message]');
            if (msgEl) msgEl.textContent = message;
        }

        if (percent !== undefined) {
            const bar = this.overlay.querySelector('[data-progress-bar]');
            const fill = this.overlay.querySelector('[data-progress-fill]');
            if (bar && fill) {
                bar.style.display = 'block';
                fill.style.width = `${Math.min(100, Math.max(0, percent))}%`;
            }
        }
    },

    hide() {
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
        }
        this._stopTimer();
    },

    _startTimer() {
        this._startTime = Date.now();
        this._timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this._startTime) / 1000);
            const elapsedEl = this.overlay?.querySelector('[data-elapsed]');
            if (elapsedEl) {
                elapsedEl.style.display = 'block';
                elapsedEl.textContent = `${elapsed}s elapsed`;
            }
        }, 1000);
    },

    _stopTimer() {
        if (this._timerInterval) {
            clearInterval(this._timerInterval);
            this._timerInterval = null;
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// ---------------------------------------------------------------------------
// Network Status & Offline Detection
// ---------------------------------------------------------------------------

const NetworkStatus = {
    isOnline: navigator.onLine,
    listeners: [],

    init() {
        window.addEventListener('online', () => this._handleStatusChange(true));
        window.addEventListener('offline', () => this._handleStatusChange(false));

        // Initial check
        if (!this.isOnline) {
            this._showOfflineBanner();
        }
    },

    onStatusChange(callback) {
        this.listeners.push(callback);
    },

    _handleStatusChange(online) {
        this.isOnline = online;

        if (online) {
            this._hideOfflineBanner();
            Toast.success('Connection restored', { duration: 3000 });
        } else {
            this._showOfflineBanner();
            Toast.warning('You are offline. Some features may be unavailable.', {
                duration: 0,
                persistent: true,
            });
        }

        this.listeners.forEach(fn => fn(online));
    },

    _showOfflineBanner() {
        if (document.getElementById('offline-banner')) return;

        const banner = document.createElement('div');
        banner.id = 'offline-banner';
        banner.className = 'fixed top-0 left-0 right-0 z-50 bg-amber-500 text-white text-center py-2 text-sm font-medium';
        banner.textContent = 'You are currently offline';
        document.body.prepend(banner);
    },

    _hideOfflineBanner() {
        const banner = document.getElementById('offline-banner');
        if (banner) banner.remove();
    },
};

// Initialize network status monitoring
NetworkStatus.init();

// ---------------------------------------------------------------------------
// Enhanced API Request with Error Handling
// ---------------------------------------------------------------------------

/**
 * Make a JSON API request with comprehensive error handling.
 * @param {string} url - The API endpoint
 * @param {string} method - HTTP method
 * @param {object|null} body - Request body
 * @param {object} options - Additional options
 * @returns {Promise<object>} - Response data or error
 */
async function apiRequestWithErrorHandling(url, method = 'GET', body = null, options = {}) {
    const {
        showProgress = false,
        progressMessage = 'Processing...',
        showErrorToast = true,
        timeout = 60000,
        retries = 0,
    } = options;

    if (showProgress) {
        Progress.show({ message: progressMessage, cancellable: true });
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    let lastError = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const opts = {
                method,
                headers: { 'Content-Type': 'application/json' },
                signal: controller.signal,
            };
            if (body) opts.body = JSON.stringify(body);

            const resp = await fetch(url, opts);
            clearTimeout(timeoutId);

            const data = await resp.json();

            if (!resp.ok) {
                const error = {
                    status: resp.status,
                    message: data.error || `Request failed with status ${resp.status}`,
                    details: data.details,
                    guidance: data.guidance,
                    recoverable: data.recoverable !== false,
                };

                if (showErrorToast && error.recoverable) {
                    Toast.error(error.message, { details: error.guidance });
                } else if (showErrorToast) {
                    ErrorModal.show({
                        title: 'Request Failed',
                        message: error.message,
                        guidance: error.guidance,
                    });
                }

                throw error;
            }

            if (showProgress) Progress.hide();
            return data;

        } catch (err) {
            lastError = err;

            if (err.name === 'AbortError') {
                const error = { status: 408, message: 'Request timed out. Please try again.' };
                if (showErrorToast) Toast.error(error.message);
                if (showProgress) Progress.hide();
                throw error;
            }

            // Network error
            if (!navigator.onLine) {
                const error = { status: 0, message: 'You are offline. Please check your connection.' };
                if (showErrorToast) Toast.error(error.message);
                if (showProgress) Progress.hide();
                throw error;
            }

            // Retry logic
            if (attempt < retries) {
                const delay = Math.pow(2, attempt) * 1000;
                await new Promise(resolve => setTimeout(resolve, delay));
                continue;
            }

            if (showProgress) Progress.hide();
            throw err;
        }
    }

    if (showProgress) Progress.hide();
    throw lastError;
}

// ---------------------------------------------------------------------------
// Form Validation Helpers
// ---------------------------------------------------------------------------

const FormValidation = {
    /**
     * Validate entry content.
     * @param {string} content - The entry content
     * @returns {object} - { valid: boolean, error: string|null }
     */
    validateEntryContent(content) {
        if (!content || !content.trim()) {
            return { valid: false, error: 'Entry content cannot be empty' };
        }
        if (content.length > 50000) {
            return { valid: false, error: 'Entry exceeds maximum length of 50,000 characters' };
        }
        const wordCount = content.trim().split(/\s+/).length;
        if (wordCount > 50000) {
            return { valid: false, error: `Entry has ${wordCount.toLocaleString()} words which may cause performance issues` };
        }
        return { valid: true, error: null };
    },

    /**
     * Show inline validation error.
     * @param {HTMLElement} input - The input element
     * @param {string} message - Error message
     */
    showError(input, message) {
        this.clearError(input);
        input.classList.add('border-red-500', 'dark:border-red-400');

        const errorEl = document.createElement('p');
        errorEl.className = 'validation-error text-xs text-red-600 dark:text-red-400 mt-1';
        errorEl.textContent = message;
        input.parentNode.appendChild(errorEl);
    },

    /**
     * Clear validation error.
     * @param {HTMLElement} input - The input element
     */
    clearError(input) {
        input.classList.remove('border-red-500', 'dark:border-red-400');
        const existing = input.parentNode.querySelector('.validation-error');
        if (existing) existing.remove();
    },
};

// ---------------------------------------------------------------------------
// Expose utilities globally
// ---------------------------------------------------------------------------

window.Toast = Toast;
window.ErrorModal = ErrorModal;
window.Progress = Progress;
window.NetworkStatus = NetworkStatus;
window.apiRequestWithErrorHandling = apiRequestWithErrorHandling;
window.FormValidation = FormValidation;

// ---------------------------------------------------------------------------
// Heart-Brain Loader Helper
// ---------------------------------------------------------------------------

const AILoader = {
    overlay: null,

    show(message = 'Thinking...') {
        if (!this.overlay) this.overlay = document.getElementById('global-loader');
        const text = document.getElementById('global-loader-text');
        if (text) text.textContent = message;
        if (this.overlay) {
            this.overlay.classList.remove('hidden');
            this.overlay.classList.add('flex');
        }
    },

    hide() {
        if (!this.overlay) this.overlay = document.getElementById('global-loader');
        if (this.overlay) {
            this.overlay.classList.add('hidden');
            this.overlay.classList.remove('flex');
        }
    },
};

window.AILoader = AILoader;

// ---------------------------------------------------------------------------
// Link Prefetching for Faster Navigation
// ---------------------------------------------------------------------------

/**
 * Prefetch pages on link hover for faster navigation.
 * Only prefetches internal links that haven't been prefetched yet.
 */
(function initLinkPrefetching() {
    const prefetched = new Set();

    document.addEventListener('mouseover', (e) => {
        const link = e.target.closest('a[href^="/"]');
        if (!link || prefetched.has(link.href)) return;

        // Skip if already on this page
        if (link.href === window.location.href) return;

        // Skip external links or hash links
        if (link.href.includes('#') || link.target === '_blank') return;

        const prefetch = document.createElement('link');
        prefetch.rel = 'prefetch';
        prefetch.href = link.href;
        document.head.appendChild(prefetch);
        prefetched.add(link.href);
    });
})();

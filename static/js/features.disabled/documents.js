/**
 * Document Manager
 * Handles document upload, management, and display
 */

class DocumentManager {
    constructor() {
        this.initElements();
        this.initEventListeners();
    }

    initElements() {
        this.docsModal = document.getElementById('docsModal');
        this.docsBtn = document.getElementById('docsBtn');
        this.closeDocsModal = document.getElementById('closeDocsModal');
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadStatus = document.getElementById('uploadStatus');
        this.docsList = document.getElementById('docsList');
        this.refreshDocsBtn = document.getElementById('refreshDocsBtn');
    }

    initEventListeners() {
        // Open modal
        this.docsBtn?.addEventListener('click', () => {
            this.docsModal?.classList.add('active');
            modalManager.push(this.docsModal, 'docs');
            this.loadDocuments();
        });

        // Close modal
        this.closeDocsModal?.addEventListener('click', () => {
            this.docsModal?.classList.remove('active');
            modalManager.pop(this.docsModal);
        });

        // Close modal when clicking outside
        this.docsModal?.addEventListener('click', (e) => {
            if (e.target === this.docsModal) {
                this.docsModal.classList.remove('active');
                modalManager.pop(this.docsModal);
            }
        });

        // File upload handlers
        this.uploadArea?.addEventListener('click', () => this.fileInput?.click());
        this.uploadArea?.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.uploadArea?.addEventListener('drop', (e) => this.handleDrop(e));
        this.fileInput?.addEventListener('change', (e) => this.handleFileSelect(e));
        this.refreshDocsBtn?.addEventListener('click', () => this.loadDocuments());
    }

    async loadDocuments() {
        console.log('DocumentManager: loadDocuments called');
    }

    async uploadFile(file) {
        console.log('DocumentManager: uploadFile called', file.name);
    }

    async deleteDocument(filename) {
        console.log('DocumentManager: deleteDocument called', filename);
    }

    handleDragOver(e) {
        e.preventDefault();
        this.uploadArea?.classList.add('drag-over');
    }

    handleDrop(e) {
        e.preventDefault();
        this.uploadArea?.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.handleFiles(files);
        }
    }

    handleFileSelect(e) {
        const files = e.target.files;
        if (files.length > 0) {
            this.handleFiles(files);
        }
    }

    async handleFiles(files) {
        for (const file of files) {
            await this.uploadFile(file);
        }
    }

    showUploadStatus(message, type = 'info') {
        if (this.uploadStatus) {
            this.uploadStatus.textContent = message;
            this.uploadStatus.className = `upload-status ${type}`;
            this.uploadStatus.style.display = 'block';

            setTimeout(() => {
                this.uploadStatus.style.display = 'none';
            }, 3000);
        }
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DocumentManager;
}

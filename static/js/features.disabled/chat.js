/**
 * Chat Manager
 * Handles chat messaging, streaming responses, and conversation display
 */

class ChatManager {
    constructor() {
        this.isLoading = false;
        this.conversationHistory = [];
        this.currentAbortController = null;
        this.lastUserQuestion = '';
        this.currentContextData = [];

        this.initElements();
        this.initEventListeners();
    }

    initElements() {
        this.chatContainer = document.getElementById('chatContainer');
        this.userInput = document.getElementById('userInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.statusEl = document.getElementById('status');
    }

    initEventListeners() {
        this.sendBtn?.addEventListener('click', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        this.clearBtn?.addEventListener('click', () => this.clearChat());

        this.userInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.userInput?.addEventListener('input', () => {
            this.autoResize();
            this.updateSendButton();
        });
    }

    autoResize() {
        if (!this.userInput) return;
        this.userInput.style.height = 'auto';
        const newHeight = Math.min(this.userInput.scrollHeight, 150);
        this.userInput.style.height = newHeight + 'px';

        if (this.userInput.scrollHeight > 150) {
            this.userInput.style.overflowY = 'auto';
        } else {
            this.userInput.style.overflowY = 'hidden';
        }
    }

    updateSendButton() {
        const hasText = this.userInput?.value.trim().length > 0;
        if (this.sendBtn) {
            this.sendBtn.disabled = !hasText || this.isLoading;
        }
    }

    async sendMessage() {
        // Implementation from script.js sendMessage()
        console.log('ChatManager: sendMessage called');
    }

    async clearChat() {
        // Implementation from script.js clearChat()
        console.log('ChatManager: clearChat called');
    }

    async checkStatus() {
        // Implementation from script.js checkStatus()
        console.log('ChatManager: checkStatus called');
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChatManager;
}

/**
 * Chat Module Index
 * 
 * Central export for all chat modules.
 */

// Re-export all chat functions
export * from './conversation.js';
export * from './message.js';
export * from './streaming.js';

// Named exports for convenience
export {
    getCurrentConversationId,
    setCurrentConversationId,
    loadConversations,
    createConversation,
    loadConversation,
    deleteConversation,
    updateConversationTitle,
    toggleBookmark
} from './conversation.js';

export {
    renderUserMessage,
    renderAssistantMessage,
    renderSystemMessage,
    createLoadingIndicator,
    updateMessageContent,
    addMessageActions
} from './message.js';

export {
    streamChatResponse,
    sendMessageWithStreaming,
    cancelStream
} from './streaming.js';

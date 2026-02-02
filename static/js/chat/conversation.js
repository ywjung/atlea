/**
 * Conversation Management
 * 
 * Handles conversation lifecycle and list management.
 */

import { get, post, del } from '../utils/http.js';
import { getItem, setItem } from '../utils/storage.js';

const CURRENT_CONVERSATION_KEY = 'current_conversation_id';

/**
 * Get current conversation ID
 * @returns {string|null}
 */
export function getCurrentConversationId() {
    return getItem(CURRENT_CONVERSATION_KEY);
}

/**
 * Set current conversation ID
 * @param {string} conversationId
 */
export function setCurrentConversationId(conversationId) {
    setItem(CURRENT_CONVERSATION_KEY, conversationId);
}

/**
 * Load all conversations for current user
 * @returns {Promise<Array>} - List of conversations
 */
export async function loadConversations() {
    try {
        const response = await get('/conversations');
        return response.conversations || [];
    } catch (error) {
        console.error('Failed to load conversations:', error);
        throw error;
    }
}

/**
 * Create new conversation
 * @param {string} title - Conversation title
 * @returns {Promise<Object>} - Created conversation
 */
export async function createConversation(title = '새 대화') {
    try {
        const response = await post('/conversations', { title });
        const conversation = response.conversation;
        
        if (conversation && conversation.id) {
            setCurrentConversationId(conversation.id);
        }
        
        return conversation;
    } catch (error) {
        console.error('Failed to create conversation:', error);
        throw error;
    }
}

/**
 * Load conversation by ID
 * @param {string} conversationId - Conversation ID
 * @returns {Promise<Object>} - Conversation with messages
 */
export async function loadConversation(conversationId) {
    try {
        const response = await get('/conversations/' + conversationId);
        setCurrentConversationId(conversationId);
        return response;
    } catch (error) {
        console.error('Failed to load conversation:', error);
        throw error;
    }
}

/**
 * Delete conversation
 * @param {string} conversationId - Conversation ID
 * @returns {Promise<void>}
 */
export async function deleteConversation(conversationId) {
    try {
        await del('/conversations/' + conversationId);
        
        if (getCurrentConversationId() === conversationId) {
            setItem(CURRENT_CONVERSATION_KEY, null);
        }
    } catch (error) {
        console.error('Failed to delete conversation:', error);
        throw error;
    }
}

/**
 * Update conversation title
 * @param {string} conversationId - Conversation ID
 * @param {string} title - New title
 * @returns {Promise<Object>}
 */
export async function updateConversationTitle(conversationId, title) {
    try {
        const response = await post('/conversations/' + conversationId, { title });
        return response;
    } catch (error) {
        console.error('Failed to update conversation title:', error);
        throw error;
    }
}

/**
 * Toggle conversation bookmark
 * @param {string} conversationId - Conversation ID
 * @returns {Promise<Object>}
 */
export async function toggleBookmark(conversationId) {
    try {
        const response = await post('/conversations/' + conversationId + '/bookmark');
        return response;
    } catch (error) {
        console.error('Failed to toggle bookmark:', error);
        throw error;
    }
}

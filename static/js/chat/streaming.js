/**
 * Streaming Response Handler
 * 
 * Handles SSE streaming for chat responses.
 */

import { renderAssistantMessage, updateMessageContent } from './message.js';

/**
 * Stream chat response from API
 * @param {string} conversationId - Conversation ID
 * @param {string} message - User message
 * @param {Object} options - Stream options
 * @param {Function} options.onChunk - Chunk callback
 * @param {Function} options.onComplete - Complete callback
 * @param {Function} options.onError - Error callback
 * @returns {EventSource} - EventSource for cancellation
 */
export function streamChatResponse(conversationId, message, options = {}) {
    const { onChunk, onComplete, onError } = options;
    
    const url = '/api/chat/stream?' + new URLSearchParams({
        conversation_id: conversationId,
        message: message
    });

    const eventSource = new EventSource(url);
    let fullText = '';

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'chunk') {
                fullText += data.content;
                if (onChunk) {
                    onChunk(data.content, fullText);
                }
            } else if (data.type === 'done') {
                eventSource.close();
                if (onComplete) {
                    onComplete(fullText, data.metadata);
                }
            } else if (data.type === 'error') {
                eventSource.close();
                if (onError) {
                    onError(new Error(data.error));
                }
            }
        } catch (error) {
            console.error('Failed to parse SSE data:', error);
        }
    };

    eventSource.onerror = (error) => {
        eventSource.close();
        if (onError) {
            onError(error);
        }
    };

    return eventSource;
}

/**
 * Send message with streaming response
 * @param {HTMLElement} chatContainer - Chat container element
 * @param {string} conversationId - Conversation ID
 * @param {string} userMessage - User message
 * @returns {Promise<string>} - Full response text
 */
export async function sendMessageWithStreaming(chatContainer, conversationId, userMessage) {
    return new Promise((resolve, reject) => {
        // Create assistant message element
        const messageElement = renderAssistantMessage('');
        chatContainer.appendChild(messageElement);

        let fullText = '';

        const stream = streamChatResponse(conversationId, userMessage, {
            onChunk: (chunk, accumulated) => {
                fullText = accumulated;
                updateMessageContent(messageElement, fullText);
                
                // Auto-scroll
                chatContainer.scrollTop = chatContainer.scrollHeight;
            },

            onComplete: (finalText, metadata) => {
                fullText = finalText;
                updateMessageContent(messageElement, fullText);
                resolve(fullText);
            },

            onError: (error) => {
                console.error('Streaming error:', error);
                updateMessageContent(messageElement, '⚠️ 응답 중 오류가 발생했습니다.');
                reject(error);
            }
        });

        // Store stream for potential cancellation
        messageElement.dataset.streamId = Date.now().toString();
        messageElement.stream = stream;
    });
}

/**
 * Cancel streaming response
 * @param {HTMLElement} messageElement - Message element with stream
 */
export function cancelStream(messageElement) {
    if (messageElement && messageElement.stream) {
        messageElement.stream.close();
        delete messageElement.stream;
    }
}

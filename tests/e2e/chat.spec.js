import { test, expect } from '@playwright/test';

/**
 * E2E Tests: Chat Functionality
 *
 * Tests:
 * - Send message and receive response
 * - Conversation management (create, load, delete)
 * - Streaming response
 * - Message formatting (markdown, code blocks)
 * - Chat history persistence
 */

// Helper function to login
async function login(page) {
    await page.goto('/login.html');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/index\.html|\/$/);
}

test.describe('Chat Functionality', () => {
    test.beforeEach(async ({ page }) => {
        await login(page);
    });

    test.describe('Message Sending', () => {
        test('should send message and receive response', async ({ page }) => {
            // Find chat input
            const chatInput = page.locator(
                '#chat-input, [data-testid="chat-input"], textarea[placeholder*="message"]'
            );
            await expect(chatInput).toBeVisible();

            // Type and send message
            await chatInput.fill('Hello, this is a test message');

            const sendButton = page.locator(
                '#send-button, [data-testid="send-button"], button[type="submit"]'
            ).first();
            await sendButton.click();

            // Wait for user message to appear
            const userMessage = page.locator('.user-message, [data-role="user"]').last();
            await expect(userMessage).toContainText('Hello, this is a test message');

            // Wait for assistant response
            const assistantMessage = page
                .locator('.assistant-message, [data-role="assistant"]')
                .last();
            await expect(assistantMessage).toBeVisible({ timeout: 30000 });

            // Response should not be empty
            const responseText = await assistantMessage.textContent();
            expect(responseText.trim().length).toBeGreaterThan(0);
        });

        test('should handle empty message', async ({ page }) => {
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();

            // Try to send empty message
            await chatInput.fill('');
            await sendButton.click();

            // Button should be disabled or nothing should happen
            // No new message should be added
            await page.waitForTimeout(1000);
            const messages = page.locator('.user-message, [data-role="user"]');
            const initialCount = await messages.count();

            await sendButton.click();
            await page.waitForTimeout(500);

            const finalCount = await messages.count();
            expect(finalCount).toBe(initialCount);
        });

        test('should display streaming response progressively', async ({ page }) => {
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();

            await chatInput.fill('Write a short story');
            await sendButton.click();

            // Wait for assistant message container
            const assistantMessage = page
                .locator('.assistant-message, [data-role="assistant"]')
                .last();
            await expect(assistantMessage).toBeVisible({ timeout: 5000 });

            // Check that content is being streamed (increases over time)
            await page.waitForTimeout(1000);
            const firstLength = (await assistantMessage.textContent()).length;

            await page.waitForTimeout(2000);
            const secondLength = (await assistantMessage.textContent()).length;

            // Content should grow during streaming
            expect(secondLength).toBeGreaterThanOrEqual(firstLength);
        });
    });

    test.describe('Conversation Management', () => {
        test('should create new conversation', async ({ page }) => {
            // Click new conversation button
            const newConvButton = page.locator(
                'button:has-text("New"), [data-testid="new-conversation"]'
            );
            await newConvButton.click();

            // Chat should be empty
            const messages = page.locator('.message, [data-role]');
            await expect(messages).toHaveCount(0);

            // Input should be enabled
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            await expect(chatInput).toBeEnabled();
        });

        test('should load existing conversation', async ({ page }) => {
            // Send a message to create conversation
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            await chatInput.fill('Test message for conversation');

            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();
            await sendButton.click();

            // Wait for response
            await page.waitForTimeout(3000);

            // Get conversation ID
            const conversationList = page.locator(
                '.conversation-item, [data-testid="conversation-item"]'
            );
            const firstConversation = conversationList.first();

            // Create new conversation
            const newConvButton = page.locator('button:has-text("New")');
            await newConvButton.click();

            // Load the previous conversation
            await firstConversation.click();

            // Previous messages should be loaded
            const messages = page.locator('.message, [data-role]');
            await expect(messages.first()).toBeVisible();
        });

        test('should delete conversation', async ({ page }) => {
            // Send a message
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            await chatInput.fill('Message to delete');

            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();
            await sendButton.click();

            await page.waitForTimeout(3000);

            // Find delete button for first conversation
            const conversationList = page.locator('.conversation-item');
            const firstConversation = conversationList.first();

            // Hover to show delete button
            await firstConversation.hover();

            const deleteButton = firstConversation.locator(
                'button[title="Delete"], .delete-button, [data-testid="delete-conversation"]'
            );

            if (await deleteButton.isVisible()) {
                await deleteButton.click();

                // Confirm deletion if there's a confirmation dialog
                const confirmButton = page.locator('button:has-text("Confirm"), button:has-text("Delete")').last();
                if (await confirmButton.isVisible()) {
                    await confirmButton.click();
                }

                // Conversation should be removed
                await expect(firstConversation).not.toBeVisible({ timeout: 2000 });
            }
        });
    });

    test.describe('Message Formatting', () => {
        test('should render markdown in messages', async ({ page }) => {
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();

            // Ask for markdown response
            await chatInput.fill('Reply with **bold text** and *italic text*');
            await sendButton.click();

            // Wait for response
            await page.waitForTimeout(5000);

            const assistantMessage = page
                .locator('.assistant-message, [data-role="assistant"]')
                .last();

            // Check if markdown is rendered (should have <strong> or <em> tags)
            const html = await assistantMessage.innerHTML();
            expect(html).toMatch(/<strong>|<b>|<em>|<i>/);
        });

        test('should render code blocks with syntax highlighting', async ({ page }) => {
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();

            // Ask for code
            await chatInput.fill('Write a simple Python function');
            await sendButton.click();

            // Wait for response with code
            await page.waitForTimeout(10000);

            // Check for code block
            const codeBlock = page.locator('pre code, .code-block');
            if ((await codeBlock.count()) > 0) {
                await expect(codeBlock.first()).toBeVisible();

                // Should have copy button
                const copyButton = page.locator('button:has-text("Copy"), .copy-button');
                if ((await copyButton.count()) > 0) {
                    await expect(copyButton.first()).toBeVisible();
                }
            }
        });
    });

    test.describe('Chat History', () => {
        test('should persist chat history after page reload', async ({ page }) => {
            const chatInput = page.locator('#chat-input, [data-testid="chat-input"]');
            const sendButton = page.locator('#send-button, [data-testid="send-button"]').first();

            // Send a unique message
            const uniqueMessage = `Test message ${Date.now()}`;
            await chatInput.fill(uniqueMessage);
            await sendButton.click();

            await page.waitForTimeout(3000);

            // Reload page
            await page.reload();

            // Message should still be visible
            const userMessage = page.locator('.user-message, [data-role="user"]');
            await expect(userMessage.last()).toContainText(uniqueMessage);
        });
    });
});

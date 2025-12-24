/**
 * Follow-up Questions Feature
 * Generates and displays contextual follow-up questions after each AI response
 */

class FollowUpQuestions {
    constructor() {
        this.currentQuestions = [];
    }

    /**
     * Generate follow-up questions based on conversation context
     * @param {string} userQuestion - The user's original question
     * @param {string} aiAnswer - The AI's answer
     * @param {Array} context - Optional conversation context
     * @returns {Promise<Array<string>>} Array of follow-up questions
     */
    async generate(userQuestion, aiAnswer, context = []) {
        try {
            const response = await fetch('/api/follow-up-questions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: userQuestion,
                    answer: aiAnswer,
                    context: context
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            this.currentQuestions = data.questions || [];
            return this.currentQuestions;

        } catch (error) {
            // Return fallback questions
            return [
                '이 내용과 관련된 추가 정보가 있나요?',
                '다른 규정과의 차이점은 무엇인가요?',
                '실제 적용 사례는 어떻게 되나요?'
            ];
        }
    }

    /**
     * Display follow-up questions in the UI
     * @param {HTMLElement} container - Parent container to append questions to
     * @param {Array<string>} questions - Array of question strings
     * @param {Function} onQuestionClick - Callback when a question is clicked
     */
    display(container, questions, onQuestionClick) {
        if (!questions || questions.length === 0) {
            return;
        }

        // Remove any existing follow-up questions in this container
        const existing = container.querySelector('.follow-up-questions');
        if (existing) {
            existing.remove();
        }

        // Create follow-up questions container
        const followUpDiv = document.createElement('div');
        followUpDiv.className = 'follow-up-questions';

        // Add header
        const header = document.createElement('div');
        header.className = 'follow-up-questions-header';
        header.innerHTML = `
            <span class="follow-up-icon">💬</span>
            <h4>후속 질문</h4>
        `;
        followUpDiv.appendChild(header);

        // Add questions list
        const questionsList = document.createElement('div');
        questionsList.className = 'follow-up-questions-list';

        questions.forEach((question, index) => {
            const questionItem = document.createElement('button');
            questionItem.className = 'follow-up-question-item';
            // Parse markdown in follow-up questions
            questionItem.innerHTML = marked.parseInline(question);
            questionItem.title = '클릭하여 질문하기';

            // Add click handler
            questionItem.addEventListener('click', () => {
                if (onQuestionClick) {
                    onQuestionClick(question);
                }
                // Add visual feedback
                questionItem.classList.add('clicked');
            });

            questionsList.appendChild(questionItem);
        });

        followUpDiv.appendChild(questionsList);
        container.appendChild(followUpDiv);
    }

    /**
     * Remove follow-up questions from container
     * @param {HTMLElement} container - Container to remove questions from
     */
    remove(container) {
        const followUpDiv = container.querySelector('.follow-up-questions');
        if (followUpDiv) {
            followUpDiv.remove();
        }
    }

    /**
     * Clear current questions
     */
    clear() {
        this.currentQuestions = [];
    }
}

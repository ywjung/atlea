/**
 * Question AutoComplete
 * Provides autocomplete suggestions based on suggested questions pool
 */

class QuestionAutoComplete {
    constructor(inputElement, suggestedQuestions = []) {
        this.input = inputElement;
        this.suggestedQuestions = suggestedQuestions;
        this.dropdownElement = null;
        this.selectedIndex = -1;
        this.isVisible = false;
        this.debounceTimer = null;
        this.minLength = 2;
        this.maxResults = 5;
        this.debounceDelay = 300; // ms

        // Build inverted index for O(1) search
        this.buildIndex();

        this.init();
    }

    /**
     * Build inverted index for fast word-based lookup
     */
    buildIndex() {
        this.wordIndex = new Map();

        this.suggestedQuestions.forEach((question, questionIdx) => {
            const words = question.toLowerCase().split(/\s+/);

            words.forEach(word => {
                // Index each word
                if (!this.wordIndex.has(word)) {
                    this.wordIndex.set(word, new Set());
                }
                this.wordIndex.get(word).add(questionIdx);

                // Also index prefixes for partial matching
                for (let i = 2; i <= word.length; i++) {
                    const prefix = word.substring(0, i);
                    if (!this.wordIndex.has(prefix)) {
                        this.wordIndex.set(prefix, new Set());
                    }
                    this.wordIndex.get(prefix).add(questionIdx);
                }
            });
        });
    }

    /**
     * Initialize autocomplete
     */
    init() {
        // Create dropdown element
        this.createDropdown();

        // Bind event listeners
        this.bindEvents();
    }

    /**
     * Create dropdown element
     */
    createDropdown() {
        this.dropdownElement = document.createElement('div');
        this.dropdownElement.className = 'autocomplete-dropdown';
        this.dropdownElement.id = 'autocompleteDropdown';
        this.dropdownElement.style.display = 'none';
        this.dropdownElement.style.position = 'fixed'; // Use fixed positioning

        // Append to body to avoid parent positioning issues
        document.body.appendChild(this.dropdownElement);
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
        // Input event with debounce
        this.input.addEventListener('input', (e) => {
            this.handleInput(e);
        });

        // Keyboard navigation
        this.input.addEventListener('keydown', (e) => {
            this.handleKeydown(e);
        });

        // Click outside to close
        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target) && !this.dropdownElement.contains(e.target)) {
                this.hide();
            }
        });

        // Window resize and scroll - reposition dropdown
        window.addEventListener('resize', () => {
            if (this.isVisible) {
                this.position();
            }
        });

        window.addEventListener('scroll', () => {
            if (this.isVisible) {
                this.position();
            }
        });

        // Focus event - ensure dropdown is positioned correctly
        this.input.addEventListener('focus', () => {
            if (this.isVisible) {
                this.position();
            }
        });
    }

    /**
     * Handle input event
     * @param {Event} e
     */
    handleInput(e) {
        const query = e.target.value.trim();

        // Clear previous debounce timer
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        // Debounce
        this.debounceTimer = setTimeout(() => {
            if (query.length >= this.minLength) {
                const matches = this.findMatches(query);
                this.show(matches);
            } else {
                this.hide();
            }
        }, this.debounceDelay);
    }

    /**
     * Handle keyboard navigation
     * @param {KeyboardEvent} e
     */
    handleKeydown(e) {
        if (!this.isVisible) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectNext();
                break;

            case 'ArrowUp':
                e.preventDefault();
                this.selectPrevious();
                break;

            case 'Enter':
                e.preventDefault();
                if (this.selectedIndex >= 0) {
                    this.selectItem(this.selectedIndex);
                }
                break;

            case 'Escape':
                e.preventDefault();
                this.hide();
                break;
        }
    }

    /**
     * Find matching questions using inverted index
     * O(1) lookup instead of O(n*m)
     * @param {string} query - Search query
     * @returns {Array} - Matched questions with scores
     */
    findMatches(query) {
        const lowerQuery = query.toLowerCase();
        const queryWords = lowerQuery.split(/\s+/).filter(w => w.length >= 2);

        if (queryWords.length === 0) {
            return [];
        }

        // Use inverted index to find candidate questions
        const candidateScores = new Map();

        queryWords.forEach(word => {
            // Look up in index (O(1))
            const questionIndices = this.wordIndex.get(word);

            if (questionIndices) {
                questionIndices.forEach(idx => {
                    const question = this.suggestedQuestions[idx];
                    const lowerQuestion = question.toLowerCase();

                    // Calculate score
                    let score = candidateScores.get(idx) || 0;

                    // Exact match (highest priority)
                    if (lowerQuestion === lowerQuery) {
                        score += 1000;
                    }
                    // Starts with query
                    else if (lowerQuestion.startsWith(lowerQuery)) {
                        score += 500;
                    }
                    // Contains full query
                    else if (lowerQuestion.includes(lowerQuery)) {
                        score += 300;
                    }
                    // Word match
                    else {
                        score += 100;
                    }

                    candidateScores.set(idx, score);
                });
            }
        });

        // Convert to results array
        const results = [];
        candidateScores.forEach((score, idx) => {
            results.push({
                question: this.suggestedQuestions[idx],
                score: score
            });
        });

        // Sort by score descending
        results.sort((a, b) => b.score - a.score);

        // Return top N results
        return results.slice(0, this.maxResults);
    }

    /**
     * Show dropdown with matches
     * @param {Array} matches - Matched questions
     */
    show(matches) {
        if (matches.length === 0) {
            this.hide();
            return;
        }

        this.dropdownElement.innerHTML = '';
        this.selectedIndex = -1;

        matches.forEach((match, index) => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            item.textContent = match.question;
            item.dataset.index = index;

            // Click handler
            item.addEventListener('click', () => {
                this.selectItem(index);
            });

            // Hover handler
            item.addEventListener('mouseenter', () => {
                this.highlightItem(index);
            });

            this.dropdownElement.appendChild(item);
        });

        this.dropdownElement.style.display = 'block';
        this.isVisible = true;
        this.position();
    }

    /**
     * Hide dropdown
     */
    hide() {
        this.dropdownElement.style.display = 'none';
        this.isVisible = false;
        this.selectedIndex = -1;
    }

    /**
     * Position dropdown below input
     */
    position() {
        const inputRect = this.input.getBoundingClientRect();

        // Use fixed positioning (no scroll offset needed)
        this.dropdownElement.style.width = `${inputRect.width}px`;
        this.dropdownElement.style.top = `${inputRect.bottom}px`;
        this.dropdownElement.style.left = `${inputRect.left}px`;
    }

    /**
     * Select next item
     */
    selectNext() {
        const items = this.dropdownElement.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        this.selectedIndex = (this.selectedIndex + 1) % items.length;
        this.highlightItem(this.selectedIndex);
    }

    /**
     * Select previous item
     */
    selectPrevious() {
        const items = this.dropdownElement.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        this.selectedIndex = this.selectedIndex <= 0
            ? items.length - 1
            : this.selectedIndex - 1;

        this.highlightItem(this.selectedIndex);
    }

    /**
     * Highlight item at index
     * @param {number} index
     */
    highlightItem(index) {
        const items = this.dropdownElement.querySelectorAll('.autocomplete-item');

        items.forEach((item, i) => {
            if (i === index) {
                item.classList.add('selected');
                // Scroll into view if needed
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('selected');
            }
        });

        this.selectedIndex = index;
    }

    /**
     * Select item and fill input
     * @param {number} index
     */
    selectItem(index) {
        const items = this.dropdownElement.querySelectorAll('.autocomplete-item');

        if (index >= 0 && index < items.length) {
            const selectedText = items[index].textContent;
            this.input.value = selectedText;

            // Trigger input event
            const event = new Event('input', { bubbles: true });
            this.input.dispatchEvent(event);

            this.hide();

            // Focus back to input
            this.input.focus();
        }
    }

    /**
     * Update suggested questions pool
     * @param {Array} questions - New questions array
     */
    updateSuggestions(questions) {
        this.suggestedQuestions = questions;
        // Rebuild index with new questions
        this.buildIndex();
    }

    /**
     * Clear autocomplete
     */
    clear() {
        this.hide();
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
    }

    /**
     * Destroy autocomplete
     */
    destroy() {
        this.clear();

        if (this.dropdownElement && this.dropdownElement.parentNode) {
            this.dropdownElement.remove();
        }

        // Remove event listeners
        // Note: In production, you'd want to store bound functions to remove them properly
    }

    /**
     * Get current configuration
     * @returns {Object}
     */
    getConfig() {
        return {
            minLength: this.minLength,
            maxResults: this.maxResults,
            debounceDelay: this.debounceDelay,
            questionsCount: this.suggestedQuestions.length
        };
    }

    /**
     * Update configuration
     * @param {Object} config
     */
    updateConfig(config) {
        if (config.minLength !== undefined) this.minLength = config.minLength;
        if (config.maxResults !== undefined) this.maxResults = config.maxResults;
        if (config.debounceDelay !== undefined) this.debounceDelay = config.debounceDelay;
    }
}

// Export for use in main script
window.QuestionAutoComplete = QuestionAutoComplete;

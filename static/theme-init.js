// Early theme initialization to prevent flash
// This script must load before body to prevent theme flash
(function() {
    try {
        const savedTheme = localStorage.getItem('theme') || 'light';
        // Validate theme value
        const theme = (savedTheme === 'dark' || savedTheme === 'light') ? savedTheme : 'light';
        document.documentElement.setAttribute('data-theme', theme);
    } catch (error) {
        // Fallback to light theme if localStorage is not available
        document.documentElement.setAttribute('data-theme', 'light');
    }
})();

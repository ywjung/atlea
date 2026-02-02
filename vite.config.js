import { defineConfig } from 'vite';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

// ES module equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Vite Configuration for Chatbot Redis
 *
 * Library mode: Bundles ES6 modules only, leaves HTML and legacy scripts as-is
 */
export default defineConfig({
    // Build in library mode for ES6 modules
    build: {
        lib: {
            entry: resolve(__dirname, 'static/js/index.js'),
            name: 'ChatbotRedis',
            formats: ['es'],
            fileName: () => 'chatbot-redis.js',
        },
        outDir: 'dist',
        emptyOutDir: true,
        sourcemap: true,
        minify: 'terser',
        terserOptions: {
            compress: {
                drop_console: false,
                drop_debugger: true,
            },
        },
        rollupOptions: {
            // External dependencies (loaded via CDN)
            external: [],
            output: {
                // Preserve module structure
                preserveModules: true,
                preserveModulesRoot: 'static/js',
                entryFileNames: '[name].js',
                assetFileNames: 'assets/[name].[ext]',
            },
        },
    },

    // Server configuration for development
    server: {
        port: 5173,
        strictPort: false,
        host: true,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            '/auth': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },

    // Preview server configuration
    preview: {
        port: 4173,
        strictPort: false,
        host: true,
    },

    // Define global constants
    define: {
        __APP_VERSION__: JSON.stringify('2.2.0'),
        __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
    },
});

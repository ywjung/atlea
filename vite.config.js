import { defineConfig } from 'vite';
import { resolve } from 'path';

/**
 * Vite Configuration for Chatbot Redis
 *
 * Build system for ES6 modular frontend
 */
export default defineConfig({
  // Root directory for source files
  root: 'static',

  // Base public path
  base: '/static/',

  // Server configuration for development
  server: {
    port: 5173,
    strictPort: false,
    host: true,
    proxy: {
      // Proxy API requests to FastAPI backend
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

  // Build configuration
  build: {
    // Output directory (relative to project root)
    outDir: '../dist/static',
    emptyOutDir: true,

    // Generate source maps for debugging
    sourcemap: true,

    // Rollup options
    rollupOptions: {
      input: {
        // Main pages
        main: resolve(__dirname, 'static/index.html'),
        login: resolve(__dirname, 'static/login.html'),
        register: resolve(__dirname, 'static/register.html'),
        profile: resolve(__dirname, 'static/profile.html'),
        'reset-password': resolve(__dirname, 'static/reset-password.html'),
        'reset-password-otp': resolve(__dirname, 'static/reset-password-otp.html'),

        // Example pages
        'example-compat-bridge': resolve(__dirname, 'static/example-compat-bridge.html'),
        'example-modular': resolve(__dirname, 'static/js/example-modular.html'),
        'test-modules': resolve(__dirname, 'static/js/test-modules.html'),
      },
      output: {
        // Asset file naming
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name.split('.');
          const ext = info[info.length - 1];
          if (/png|jpe?g|svg|gif|tiff|bmp|ico/i.test(ext)) {
            return `assets/images/[name]-[hash][extname]`;
          } else if (/woff2?|ttf|eot/i.test(ext)) {
            return `assets/fonts/[name]-[hash][extname]`;
          }
          return `assets/[name]-[hash][extname]`;
        },
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
      },
    },

    // Chunk size warning limit
    chunkSizeWarningLimit: 1000,

    // Minification
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: false, // Keep console for logging
        drop_debugger: true,
      },
    },
  },

  // Optimization
  optimizeDeps: {
    include: [
      // Pre-bundle dependencies
    ],
  },

  // CSS configuration
  css: {
    devSourcemap: true,
  },

  // Define global constants
  define: {
    __APP_VERSION__: JSON.stringify('2.2.0'),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },

  // Preview server configuration
  preview: {
    port: 4173,
    strictPort: false,
    host: true,
  },
});

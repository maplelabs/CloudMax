
  import { defineConfig, loadEnv } from 'vite';
  import react from '@vitejs/plugin-react-swc';
  import path from 'path';

  export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');

    return {
    plugins: [react()],
    define: {
      'import.meta.env.BACKEND_URL': JSON.stringify(env.BACKEND_URL),
      'import.meta.env.BACKEND_WS_URL': JSON.stringify(env.BACKEND_WS_URL),
    },
    resolve: {
      extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    esbuild: {
      logOverride: { 'this-is-undefined-in-esm': 'silent' },
      legalComments: 'none',
    },
    build: {
      target: 'esnext',
      outDir: 'dist',
    },
    server: {
      port: 3000,
      host: true,
      proxy: {
        '/v1': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/v1/, ''),
        },
      },
    }
  };
});
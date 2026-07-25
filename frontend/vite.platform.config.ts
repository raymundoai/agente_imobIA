import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    {
      name: "platform-root-entry",
      configureServer(server) {
        server.middlewares.use((request, _response, next) => {
          if (request.url === "/") request.url = "/platform.html";
          next();
        });
      },
    },
    react(),
  ],
  build: {
    outDir: "dist-platform",
    rollupOptions: {
      input: "platform.html",
      output: {
        manualChunks: {
          icons: ["lucide-react"],
        },
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});

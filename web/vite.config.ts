import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发模式：前端 5173 → 后端 8000 代理（避免跨域）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});

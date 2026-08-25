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
    chunkSizeWarningLimit: 900, // antd 按需引入为后续优化项
    // 按库拆分 chunk，减小首屏体积与告警
    rollupOptions: {
      output: {
        manualChunks: {
          antd: ["antd", "@ant-design/icons"],
          react: ["react", "react-dom"],
        },
      },
    },
  },
});

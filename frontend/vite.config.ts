import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5183,
    // 開發模式下 API 轉發到 FastAPI 後端
    proxy: {
      "/api": "http://127.0.0.1:8710",
    },
  },
});

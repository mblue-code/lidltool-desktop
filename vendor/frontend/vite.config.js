import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { resolve } from "path";
export default defineConfig({
    plugins: [tailwindcss(), react()],
    resolve: {
        alias: {
            "@mariozechner/pi-ai": resolve(process.cwd(), "src/shims/pi-ai.ts"),
            "@": resolve(process.cwd(), "src")
        }
    },
    server: {
        port: 5173,
        proxy: {
            "/api": "http://127.0.0.1:8000"
        }
    }
});

import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      sourcemap: "hidden"
    },
    resolve: {
      alias: {
        "@shared": resolve(__dirname, "src/shared")
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      sourcemap: "hidden"
    },
    resolve: {
      alias: {
        "@shared": resolve(__dirname, "src/shared")
      }
    }
  },
  renderer: {
    plugins: [react()],
    build: {
      sourcemap: "hidden"
    },
    resolve: {
      alias: {
        "@renderer": resolve(__dirname, "src/renderer"),
        "@shared": resolve(__dirname, "src/shared")
      }
    }
  }
});

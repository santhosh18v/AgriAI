import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Component tests (*.test.tsx) need JSX transformed. Vite/Rolldown's
  // default Oxc transform otherwise inherits tsconfig.json's `jsx:
  // "preserve"` (set for Next.js's own SWC compiler) and leaves JSX syntax
  // untransformed, which then fails Vite's import-analysis step. This is
  // set directly instead of via @vitejs/plugin-react, since that package's
  // .d.ts requires a newer TypeScript than this project pins (breaks `tsc
  // --noEmit`).
  oxc: {
    jsx: { runtime: "automatic" },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});

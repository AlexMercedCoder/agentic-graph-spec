import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/cli.ts"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  splitting: false,
  target: "node20",
  noExternal: ["canonicalize"],
  banner: {
    js: "#!/usr/bin/env node",
  },
});

import { resolve } from "node:path";

import { loadGraph, ParseError } from "./parse.js";
import { validateGraph } from "./validate.js";

async function main(): Promise<number> {
  const arguments_ = process.argv.slice(2);
  const strictIndex = arguments_.indexOf("--strict");
  const strict = strictIndex >= 0;
  if (strict) arguments_.splice(strictIndex, 1);
  if (arguments_.length === 0) {
    console.error("usage: ags-validate [--strict] <graph.agraph.yaml|graph.agraph.json> [...]");
    return 2;
  }
  let failed = false;
  for (const argument of arguments_) {
    const path = resolve(argument);
    try {
      const report = validateGraph(await loadGraph(path));
      for (const finding of report.findings) {
        const location = finding.pointer ? ` at ${finding.pointer}` : "";
        console.error(`[${finding.severity.toUpperCase()}] ${finding.code}: ${finding.message}${location}`);
      }
      if (!report.ok || (strict && report.warnings.length > 0)) failed = true;
      else console.log(`${argument}: valid`);
    } catch (error) {
      const code = error instanceof ParseError ? error.code : "AG001";
      console.error(`[ERROR] ${code}: ${(error as Error).message}`);
      failed = true;
    }
  }
  return failed ? 1 : 0;
}

main().then(
  (code) => {
    process.exitCode = code;
  },
  (error: unknown) => {
    console.error(error);
    process.exitCode = 1;
  },
);

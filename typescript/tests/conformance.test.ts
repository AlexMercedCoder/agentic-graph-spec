import { readFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  graphDigest,
  parseExpression,
  parseGraph,
  planGraph,
  validateGraph,
  validatePath,
} from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const repository = resolve(here, "../..");

const examples = [
  "minimal.agraph.yaml",
  "library-v1-release.agraph.yaml",
  "library-v1-release.agraph.json",
  "test-repair-loop.agraph.yaml",
  "docs-site-refresh.agraph.yaml",
  "link-audit.agraph.yaml",
];

describe("AGS 1.0 conformance corpus", () => {
  for (const name of examples) {
    it(`accepts ${name}`, async () => {
      const text = await readFile(resolve(repository, "examples", name), "utf8");
      const document = parseGraph(text, name.endsWith(".json") ? "json" : "yaml");
      const report = validateGraph(document);
      expect(report.errors, report.errors.map((error) => `${error.code}: ${error.message}`).join("\n")).toEqual([]);
    });
  }

  for (const [name, code] of [
    ["ag111-cycle.agraph.yaml", "AG111"],
    ["ag113-unknown-node.agraph.yaml", "AG113"],
    ["ag131-recursive-subgraph.agraph.yaml", "AG131"],
    ["ag141-tier-mismatch.agraph.yaml", "AG141"],
    ["ag201-forward-read.agraph.yaml", "AG201"],
    ["ag204-bad-expression.agraph.yaml", "AG204"],
    ["ag205-secret-reference.agraph.yaml", "AG205"],
  ] as const) {
    it(`rejects ${name} with ${code}`, async () => {
      const text = await readFile(resolve(repository, "conformance/invalid", name), "utf8");
      const report = validateGraph(parseGraph(text));
      expect(report.errors.map((finding) => finding.code)).toContain(code);
    });
  }
});

describe("portable parsing and planning", () => {
  it("gives canonical JSON and YAML the same identity", async () => {
    const yaml = parseGraph(await readFile(resolve(repository, "examples/library-v1-release.agraph.yaml"), "utf8"));
    const json = parseGraph(await readFile(resolve(repository, "examples/library-v1-release.agraph.json"), "utf8"), "json");
    expect(yaml).toEqual(json);
    expect(graphDigest(yaml)).toBe(graphDigest(json));
    expect(graphDigest(json)).toBe("sha256-ZaKZTS3i9OBDZNnKSNF2ZI22BZmOh1CcVNM0VZGDe+A=");
  });

  it("uses YAML 1.2 core booleans and rejects duplicate keys", () => {
    expect(parseGraph("value: yes\nenabled: true\n")).toEqual({ value: "yes", enabled: true });
    expect(() => parseGraph("value: 1\nvalue: 2\n")).toThrow(/unique/i);
  });

  it("builds a deterministic Level 0 plan", async () => {
    const document = parseGraph(await readFile(resolve(repository, "examples/minimal.agraph.yaml"), "utf8"));
    const first = planGraph(document);
    const second = planGraph(document);
    expect(first).toEqual(second);
    expect(first.executable).toBe(false);
    expect(first.order).toHaveLength(Object.keys(document.nodes as object).length);
  });

  it("provides the Python-compatible validatePath convenience API", async () => {
    expect((await validatePath(resolve(repository, "examples/minimal.agraph.yaml"))).ok).toBe(true);
  });

  it("parses AGX and collects calls and references", () => {
    expect(parseExpression("succeeded('build') && len(nodes.build.outputs.files) > 0")).toEqual({
      calls: [
        { name: "succeeded", arity: 1 },
        { name: "len", arity: 1 },
      ],
      references: [["nodes", "build", "outputs", "files"]],
    });
  });
});

it("keeps fixture names visible in test diagnostics", () => {
  expect(basename(repository)).toBe("agentic-graph-spec");
});

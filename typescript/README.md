# Agentic Graph Specification for TypeScript

TypeScript support for [Agentic Graph Specification 1.0](../SPEC.md). The package validates the
normative JSON Schema and semantic conformance rules, computes RFC 8785 graph identities, parses
AGX expressions, and produces deterministic Level 0 plans. It does not execute graph nodes.

```bash
npm install agentic-graph-spec
```

```ts
import { loadGraph, planGraph, validateGraph } from "agentic-graph-spec";

const graph = await loadGraph("release.agraph.yaml");
const report = validateGraph(graph);
if (!report.ok) throw new Error(report.errors.map((item) => item.message).join("\n"));

const plan = planGraph(graph);
console.log(plan.graphDigest, plan.order);
```

The loader uses YAML 1.2 core semantics and rejects duplicate mapping keys. Both ESM and CommonJS
consumers are supported on Node.js 20 or newer.

import { graphDigest } from "./canonical.js";
import type { EffectiveEdge, GraphPlan, JsonObject } from "./types.js";

type RecordValue = Record<string, unknown>;

function isRecord(value: unknown): value is RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function records(value: unknown): Record<string, RecordValue> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, RecordValue] => isRecord(entry[1])));
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function graphEffectiveEdges(document: JsonObject): EffectiveEdge[] {
  const nodes = records(document.nodes);
  const edges: EffectiveEdge[] = [];
  for (const [nodeId, node] of Object.entries(nodes)) {
    for (const dependency of strings(node.depends_on)) edges.push({ from: dependency, to: nodeId, kind: "sequence" });
  }
  if (Array.isArray(document.edges)) {
    for (const raw of document.edges) {
      if (!isRecord(raw) || typeof raw.from !== "string" || typeof raw.to !== "string") continue;
      const edge: EffectiveEdge = { from: raw.from, to: raw.to, kind: typeof raw.kind === "string" ? raw.kind : "sequence" };
      if (typeof raw.when === "string") edge.when = raw.when;
      edges.push(edge);
    }
  }
  const seen = new Set<string>();
  return edges.filter((edge) => {
    const key = `${edge.from}\u0000${edge.to}\u0000${edge.kind}\u0000${edge.when ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function topologicalOrder(document: JsonObject): string[] {
  const ids = Object.keys(records(document.nodes));
  const edges = graphEffectiveEdges(document).filter((edge) => ids.includes(edge.from) && ids.includes(edge.to));
  const incoming = new Map(ids.map((id) => [id, 0]));
  const outgoing = new Map(ids.map((id) => [id, [] as string[]]));
  for (const edge of edges) {
    incoming.set(edge.to, (incoming.get(edge.to) ?? 0) + 1);
    outgoing.get(edge.from)?.push(edge.to);
  }
  const ready = ids.filter((id) => incoming.get(id) === 0).sort();
  const order: string[] = [];
  while (ready.length > 0) {
    const current = ready.shift();
    if (!current) break;
    order.push(current);
    for (const next of (outgoing.get(current) ?? []).sort()) {
      const count = (incoming.get(next) ?? 0) - 1;
      incoming.set(next, count);
      if (count === 0) {
        ready.push(next);
        ready.sort();
      }
    }
  }
  if (order.length !== ids.length) throw new Error("cannot plan a cyclic graph");
  return order;
}

function fragmentExecutions(fragment: RecordValue, named: Record<string, RecordValue>, active = new Set<string>()): number {
  return nodeExecutions(records(fragment.nodes), named, active);
}

function nodeExecutions(nodes: Record<string, RecordValue>, named: Record<string, RecordValue>, active = new Set<string>()): number {
  let total = 0;
  for (const node of Object.values(nodes)) {
    total += 1;
    const type = typeof node.type === "string" ? node.type : "task";
    if (!["loop", "map", "subgraph"].includes(type)) continue;
    const block = isRecord(node[type]) ? node[type] : {};
    let body: RecordValue | undefined;
    if (type === "subgraph" && isRecord(block.inline)) body = block.inline;
    else if ((type === "loop" || type === "map") && isRecord(block.body)) body = block.body;
    const use = typeof block.use === "string" ? block.use : undefined;
    if (!body && use && !active.has(use)) body = named[use];
    if (!body) continue;
    const nested = fragmentExecutions(body, named, use ? new Set(active).add(use) : active);
    if (type === "loop") total += nested * (typeof block.max_iterations === "number" ? block.max_iterations : 1);
    else if (type === "map") total += nested * (typeof block.max_items === "number" ? block.max_items : 1);
    else total += nested;
  }
  return total;
}

export function planGraph(document: JsonObject): GraphPlan {
  const nodes = records(document.nodes);
  const edges = graphEffectiveEdges(document);
  const order = topologicalOrder(document);
  const entrypoints = strings(document.entrypoints);
  const outgoing = new Map(Object.keys(nodes).map((id) => [id, [] as string[]]));
  for (const edge of edges) outgoing.get(edge.from)?.push(edge.to);
  const reachableSet = new Set<string>();
  const stack = [...entrypoints];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || reachableSet.has(current)) continue;
    reachableSet.add(current);
    stack.push(...(outgoing.get(current) ?? []));
  }
  const tierHistogram: Record<string, number> = {};
  const unsupported = new Set<string>();
  for (const node of Object.values(nodes)) {
    const intelligence = isRecord(node.intelligence) ? node.intelligence : {};
    const tier = typeof intelligence.tier === "string" ? intelligence.tier : "unspecified";
    tierHistogram[tier] = (tierHistogram[tier] ?? 0) + 1;
    const type = typeof node.type === "string" ? node.type : "task";
    if (type !== "task" && type !== "gate") unsupported.add(type);
  }
  return {
    graphId: typeof document.id === "string" ? document.id : "",
    graphDigest: graphDigest(document),
    order,
    entrypoints,
    effectiveEdges: edges,
    reachable: order.filter((id) => reachableSet.has(id)),
    unreachable: order.filter((id) => !reachableSet.has(id)),
    tierHistogram,
    worstCaseNodeExecutions: nodeExecutions(nodes, records(document.subgraphs)),
    executable: false,
    unsupportedFeatures: [...unsupported].sort(),
  };
}

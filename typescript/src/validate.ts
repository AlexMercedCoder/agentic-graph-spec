import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import graphSchema from "../../schema/agentic-graph-1.0.schema.json";

import { AGX_FUNCTIONS, parseExpression } from "./agx.js";
import type { EffectiveEdge, Finding, JsonObject, JsonValue, ValidationReport } from "./types.js";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validateSchema = ajv.compile(graphSchema);

const TIER_LEVEL: Readonly<Record<string, number>> = {
  minimal: 1,
  standard: 2,
  advanced: 3,
  frontier: 4,
};

type RecordValue = Record<string, unknown>;

interface Scope {
  name: string;
  pointer: string;
  nodes: Record<string, RecordValue>;
  edges: RecordValue[];
  entrypoints: string[];
  isRoot: boolean;
  paramNames: Set<string>;
  outputNames: Set<string>;
  outputsSpec: RecordValue;
  extraBindings: Set<string>;
  predecessors: Map<string, Set<string>>;
  effectiveEdges: EffectiveEdge[];
}

function isRecord(value: unknown): value is RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function record(value: unknown): RecordValue {
  return isRecord(value) ? value : {};
}

function records(value: unknown): Record<string, RecordValue> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, RecordValue] => isRecord(entry[1])));
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function recordArray(value: unknown): RecordValue[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is RecordValue => isRecord(item));
}

function declaredOutputs(node: RecordValue): Set<string> {
  const names = new Set(Object.keys(records(node.outputs)));
  const type = typeof node.type === "string" ? node.type : "task";
  if (type === "decision" || type === "gate") names.add("decision");
  if (type === "gate") for (const name of Object.keys(record(record(node.gate).collect))) names.add(name);
  if (type === "loop") for (const name of Object.keys(record(record(node.loop).collect))) names.add(name);
  if (type === "map") for (const name of Object.keys(record(record(node.map).collect))) names.add(name);
  if (type === "subgraph") for (const name of Object.keys(record(record(node.subgraph).outputs_from))) names.add(name);
  return names;
}

function add(findings: Finding[], code: string, severity: "error" | "warning", message: string, pointer = ""): void {
  findings.push({ code, severity, message, pointer });
}

function allStrings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(allStrings);
  if (isRecord(value)) return Object.values(value).flatMap(allStrings);
  return [];
}

function checkUnreadOutputs(scopes: Scope[], document: JsonObject, findings: Finding[]): void {
  const graphReads = new Set<string>();
  for (const text of allStrings(document)) {
    for (const match of text.matchAll(/nodes\.([A-Za-z_][\w-]*)\.outputs\.([A-Za-z_][\w-]*)/g)) graphReads.add(`${match[1]}\u0000${match[2]}`);
  }
  for (const scope of scopes) for (const [nodeId, node] of Object.entries(scope.nodes)) {
    const read = new Set(graphReads);
    for (const text of allStrings(node)) {
      for (const match of text.matchAll(/(?:self|nodes\.self)\.outputs\.([A-Za-z_][\w-]*)/g)) read.add(`${nodeId}\u0000${match[1]}`);
    }
    for (const name of Object.keys(records(node.outputs))) {
      if (!read.has(`${nodeId}\u0000${name}`)) add(findings, "AG904", "warning", `output ${JSON.stringify(name)} of node ${JSON.stringify(nodeId)} is never read`, `${scope.pointer}/nodes/${nodeId}/outputs/${name}`);
    }
  }
}

function schemaCode(error: ErrorObject): string {
  if (error.keyword === "additionalProperties") return "AG003";
  if (error.keyword === "enum") return "AG004";
  if (error.instancePath.includes("/edges/") && ["not", "allOf"].includes(error.keyword)) return "AG103";
  if (error.instancePath.includes("/inputs/") && ["oneOf", "maxProperties"].includes(error.keyword)) return "AG104";
  return "AG001";
}

function effectiveEdges(nodes: Record<string, RecordValue>, explicit: RecordValue[]): EffectiveEdge[] {
  const result: EffectiveEdge[] = [];
  for (const [nodeId, node] of Object.entries(nodes)) {
    for (const dependency of strings(node.depends_on)) {
      result.push({ from: dependency, to: nodeId, kind: "sequence" });
    }
  }
  for (const edge of explicit) {
    if (typeof edge.from !== "string" || typeof edge.to !== "string") continue;
    const next: EffectiveEdge = {
      from: edge.from,
      to: edge.to,
      kind: typeof edge.kind === "string" ? edge.kind : "sequence",
    };
    if (typeof edge.when === "string") next.when = edge.when;
    result.push(next);
  }
  const seen = new Set<string>();
  return result.filter((edge) => {
    const key = `${edge.from}\u0000${edge.to}\u0000${edge.kind}\u0000${edge.when ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function findCycle(ids: string[], edges: EffectiveEdge[]): string[] | undefined {
  const outgoing = new Map(ids.map((id) => [id, [] as string[]]));
  for (const edge of edges) outgoing.get(edge.from)?.push(edge.to);
  const state = new Map(ids.map((id) => [id, 0]));
  const path: string[] = [];
  const visit = (id: string): string[] | undefined => {
    state.set(id, 1);
    path.push(id);
    for (const next of outgoing.get(id) ?? []) {
      if (state.get(next) === 1) return [...path.slice(path.indexOf(next)), next];
      if (state.get(next) === 0) {
        const found = visit(next);
        if (found) return found;
      }
    }
    path.pop();
    state.set(id, 2);
    return undefined;
  };
  for (const id of [...ids].sort()) {
    if (state.get(id) === 0) {
      const found = visit(id);
      if (found) return found;
    }
  }
  return undefined;
}

function transitivePredecessors(ids: string[], edges: EffectiveEdge[]): Map<string, Set<string>> {
  const direct = new Map(ids.map((id) => [id, new Set<string>()]));
  for (const edge of edges) direct.get(edge.to)?.add(edge.from);
  const memo = new Map<string, Set<string>>();
  const resolve = (id: string, active = new Set<string>()): Set<string> => {
    const cached = memo.get(id);
    if (cached) return cached;
    if (active.has(id)) return new Set();
    const result = new Set<string>();
    const nextActive = new Set(active).add(id);
    for (const parent of direct.get(id) ?? []) {
      result.add(parent);
      for (const ancestor of resolve(parent, nextActive)) result.add(ancestor);
    }
    memo.set(id, result);
    return result;
  };
  for (const id of ids) resolve(id);
  return memo;
}

function addFragmentScopes(scopes: Scope[], fragment: RecordValue, pointer: string, name: string, extraBindings = new Set<string>(), inheritedParams = new Set<string>()): void {
  const nodes = records(fragment.nodes);
  const ownParams = new Set(Object.keys(records(fragment.params)));
  const scope: Scope = {
    name,
    pointer,
    nodes,
    edges: recordArray(fragment.edges),
    entrypoints: strings(fragment.entrypoints),
    isRoot: false,
    paramNames: ownParams.size > 0 ? ownParams : inheritedParams,
    outputNames: new Set(Object.keys(records(fragment.outputs))),
    outputsSpec: record(fragment.outputs),
    extraBindings,
    predecessors: new Map(),
    effectiveEdges: [],
  };
  scopes.push(scope);
  collectInlineScopes(scopes, nodes, pointer, scope.paramNames);
}

function collectInlineScopes(scopes: Scope[], nodes: Record<string, RecordValue>, base: string, inheritedParams = new Set<string>()): void {
  for (const [nodeId, node] of Object.entries(nodes)) {
    const type = typeof node.type === "string" ? node.type : "task";
    if (!["loop", "map", "subgraph"].includes(type)) continue;
    const block = record(node[type]);
    const inline = type === "subgraph" ? block.inline : block.body;
    const extra = type === "loop"
      ? new Set(["loop"])
      : type === "map"
        ? new Set([typeof block.as === "string" ? block.as : "item", typeof block.index_as === "string" ? block.index_as : "index"])
        : new Set<string>();
    if (isRecord(inline)) addFragmentScopes(scopes, inline, `${base}/nodes/${nodeId}/${type}/${type === "subgraph" ? "inline" : "body"}`, `${nodeId}.${type}`, extra, inheritedParams);
  }
}

function collectScopes(document: JsonObject): Scope[] {
  const rootNodes = records(document.nodes);
  const scopes: Scope[] = [{
    name: "<root>",
    pointer: "",
    nodes: rootNodes,
    edges: recordArray(document.edges),
    entrypoints: strings(document.entrypoints),
    isRoot: true,
    paramNames: new Set(Object.keys(records(document.params))),
    outputNames: new Set(Object.keys(records(document.outputs))),
    outputsSpec: record(document.outputs),
    extraBindings: new Set(),
    predecessors: new Map(),
    effectiveEdges: [],
  }];
  collectInlineScopes(scopes, rootNodes, "", scopes[0]!.paramNames);
  for (const [name, fragment] of Object.entries(records(document.subgraphs))) {
    addFragmentScopes(scopes, fragment, `/subgraphs/${name}`, `subgraphs.${name}`, new Set(), scopes[0]!.paramNames);
  }
  return scopes;
}

function checkNamedRecursion(document: JsonObject, findings: Finding[]): void {
  const fragments = records(document.subgraphs);
  const dependencies = new Map<string, Set<string>>();
  for (const [name, fragment] of Object.entries(fragments)) {
    const refs = new Set<string>();
    for (const node of Object.values(records(fragment.nodes))) {
      for (const blockName of ["loop", "map", "subgraph"]) {
        const use = record(node[blockName]).use;
        if (typeof use === "string") refs.add(use);
      }
    }
    dependencies.set(name, refs);
  }
  const visited = new Set<string>();
  const active: string[] = [];
  const visit = (name: string): void => {
    const position = active.indexOf(name);
    if (position >= 0) {
      add(findings, "AG131", "error", `recursive subgraph reference: ${[...active.slice(position), name].join(" -> ")}`, `/subgraphs/${name}`);
      return;
    }
    if (visited.has(name) || !dependencies.has(name)) return;
    active.push(name);
    for (const dependency of [...(dependencies.get(name) ?? [])].sort()) visit(dependency);
    active.pop();
    visited.add(name);
  };
  for (const name of [...dependencies.keys()].sort()) visit(name);
}

function validateExpression(text: string, pointer: string, findings: Finding[], scope?: Scope, nodeId?: string, document?: JsonObject): void {
  if (templatePattern.test(text)) {
    templatePattern.lastIndex = 0;
    add(findings, "AG211", "error", "'${{ }}' interpolation used in expression position", pointer);
    return;
  }
  templatePattern.lastIndex = 0;
  try {
    const parsed = parseExpression(text);
    for (const call of parsed.calls) {
      const expected = AGX_FUNCTIONS[call.name];
      if (expected === undefined) {
        add(findings, "AG204", "error", `unknown function ${JSON.stringify(call.name)}`, pointer);
      } else {
        const valid = typeof expected === "number"
          ? call.arity === expected
          : call.arity >= expected[0] && call.arity <= expected[1];
        if (!valid) add(findings, "AG204", "error", `function ${call.name} received ${call.arity} argument(s)`, pointer);
      }
    }
    for (const parts of parsed.references) {
      const root = parts[0];
      if (root === "secrets") {
        add(findings, "AG205", "error", "expressions must not reference secrets.*", pointer);
        continue;
      }
      if (!scope) continue;
      if (root === "graph") {
        if (parts[1] && !["id", "title", "objective", "version", "description"].includes(parts[1])) add(findings, "AG203", "error", `unknown graph field ${JSON.stringify(parts[1])}`, pointer);
        continue;
      }
      if (root === "params") {
        if (parts[1] && !scope.paramNames.has(parts[1])) add(findings, "AG203", "error", `undeclared param ${JSON.stringify(parts[1])}`, pointer);
        continue;
      }
      if (root === "context" || root === "attachments") {
        const declared = root === "context"
          ? new Set(Object.keys(record(document?.context)))
          : new Set(recordArray(document?.attachments).map((attachment) => attachment.name).filter((name): name is string => typeof name === "string"));
        if (parts[1] && !declared.has(parts[1])) add(findings, "AG203", "error", `undeclared ${root === "context" ? "context key" : "attachment"} ${JSON.stringify(parts[1])}`, pointer);
        continue;
      }
      if (root === "env") {
        const declared = nodeId ? new Set(strings(record(scope.nodes[nodeId]?.requirements).environment)) : new Set<string>();
        if (parts[1] && !declared.has(parts[1])) add(findings, "AG203", "error", `env.${parts[1]} is not declared in requirements.environment`, pointer);
        continue;
      }
      if (root === "outputs") {
        if (!scope.isRoot || nodeId) add(findings, "AG203", "error", "'outputs' is only available in graph-level scope", pointer);
        else if (parts[1] && !scope.outputNames.has(parts[1])) add(findings, "AG203", "error", `undeclared graph output ${JSON.stringify(parts[1])}`, pointer);
        continue;
      }
      if (root === "loop" || root === "map") {
        if (!scope.extraBindings.has(root)) add(findings, "AG203", "error", `'${root}' is only available inside a ${root} body`, pointer);
        continue;
      }
      if (root === "self") {
        if (!nodeId) add(findings, "AG203", "error", "'self' is only available within a node", pointer);
        else if (parts[1] === "outputs" && parts[2] && !declaredOutputs(scope.nodes[nodeId] ?? {}).has(parts[2])) add(findings, "AG206", "error", `self.outputs.${parts[2]} is not a declared output`, pointer);
        else if (parts[1] && !["id", "attempt", "inputs", "outputs"].includes(parts[1])) add(findings, "AG203", "error", `unknown self field ${JSON.stringify(parts[1])}`, pointer);
        continue;
      }
      if (root === "nodes") {
        const target = parts[1];
        if (target && !scope.nodes[target]) {
          add(findings, scope.isRoot ? "AG203" : "AG202", "error", `unknown node ${JSON.stringify(target)}`, pointer);
        } else if (target && parts[2] === "outputs" && parts[3] && !declaredOutputs(scope.nodes[target] ?? {}).has(parts[3])) {
          add(findings, "AG206", "error", `node ${JSON.stringify(target)} does not declare output ${JSON.stringify(parts[3])}`, pointer);
        } else if (parts[2] && !["status", "outputs", "attempts", "duration_seconds", "decision"].includes(parts[2])) {
          add(findings, "AG203", "error", `unknown node field ${JSON.stringify(parts[2])}`, pointer);
        } else if (nodeId && target && target !== nodeId && !scope.predecessors.get(nodeId)?.has(target)) {
          add(findings, "AG201", "error", `node ${JSON.stringify(nodeId)} reads output of non-predecessor ${JSON.stringify(target)}`, pointer);
        }
        continue;
      }
      if (!scope.extraBindings.has(root ?? "")) add(findings, "AG203", "error", `unknown reference root ${JSON.stringify(root)}`, pointer);
    }
  } catch (error) {
    add(findings, "AG204", "error", `invalid expression: ${(error as Error).message}`, pointer);
  }
}

const templatePattern = /\$\{\{(.*?)\}\}/gs;

function checkNodeExpressions(scope: Scope, nodeId: string, node: RecordValue, pointer: string, findings: Finding[], document: JsonObject, scopes: Scope[]): void {
  const expression = (text: unknown, location: string, targetScope = scope, targetNode: string | null = nodeId): void => {
    if (typeof text === "string") validateExpression(text, location, findings, targetScope, targetNode ?? undefined, document);
  };
  const template = (text: unknown, location: string, targetScope = scope, targetNode: string | null = nodeId): void => {
    if (typeof text === "string") for (const match of text.matchAll(templatePattern)) expression(match[1] ?? "", location, targetScope, targetNode);
  };
  const success = (value: unknown, base: string): void => {
    recordArray(record(value).criteria).forEach((criterion, index) => {
      const criterionPointer = `${base}/criteria/${index}`;
      expression(criterion.expr, `${criterionPointer}/expr`);
      expression(criterion.target, `${criterionPointer}/target`);
      (Array.isArray(criterion.inputs) ? criterion.inputs : []).forEach((input, inputIndex) => expression(input, `${criterionPointer}/inputs/${inputIndex}`));
      template(criterion.rubric, `${criterionPointer}/rubric`);
      template(criterion.prompt, `${criterionPointer}/prompt`);
      if (["artifact_present", "json_schema", "regex"].includes(String(criterion.kind)) && typeof criterion.output === "string" && !declaredOutputs(node).has(criterion.output)) {
        add(findings, "AG206", "error", `criterion references undeclared output ${JSON.stringify(criterion.output)}`, criterionPointer);
      }
    });
  };
  for (const [name, input] of Object.entries(records(node.inputs))) {
    expression(input.from, `${pointer}/inputs/${name}/from`);
    template(input.template, `${pointer}/inputs/${name}/template`);
  }
  expression(node.when, `${pointer}/when`);
  template(node.instructions, `${pointer}/instructions`);
  success(node.success, `${pointer}/success`);
  recordArray(node.human).forEach((checkpoint, index) => {
    expression(checkpoint.when, `${pointer}/human/${index}/when`);
    template(checkpoint.prompt, `${pointer}/human/${index}/prompt`);
  });
  const failure = record(node.failure);
  recordArray(failure.fallback).forEach((step, index) => expression(step.when, `${pointer}/failure/fallback/${index}/when`));
  template(record(failure.escalation).message, `${pointer}/failure/escalation/message`);
  const type = typeof node.type === "string" ? node.type : "task";
  const block = record(node[type]);
  if (type === "gate") {
    template(block.prompt, `${pointer}/gate/prompt`);
    (Array.isArray(block.present) ? block.present : []).forEach((value, index) => expression(value, `${pointer}/gate/present/${index}`));
  } else if (type === "decision") {
    template(block.question, `${pointer}/decision/question`);
    recordArray(block.branches).forEach((branch, index) => expression(branch.when, `${pointer}/decision/branches/${index}/when`));
  } else if (type === "loop" || type === "map") {
    const bodyPointer = `${pointer}/${type}/body`;
    const body = isRecord(block.body)
      ? scopes.find((candidate) => candidate.pointer === bodyPointer)
      : typeof block.use === "string"
        ? scopes.find((candidate) => candidate.pointer === `/subgraphs/${block.use}`)
        : undefined;
    if (type === "loop") expression(block.condition, `${pointer}/loop/condition`, body ?? scope, null);
    else expression(block.over, `${pointer}/map/over`);
    for (const [name, value] of Object.entries(record(block.collect))) expression(value, `${pointer}/${type}/collect/${name}`, body ?? scope, null);
    if (type === "loop" && body) for (const [source, target] of Object.entries(record(block.carry))) {
      const produced = new Set(Object.values(body.nodes).flatMap((bodyNode) => [...declaredOutputs(bodyNode)]));
      if (!produced.has(source)) add(findings, "AG206", "error", `carry source ${JSON.stringify(source)} is not produced by any node in the loop body`, `${pointer}/loop/carry/${source}`);
      if (typeof target === "string" && !body.paramNames.has(target)) add(findings, "AG203", "error", `carry target ${JSON.stringify(target)} is not a param of the loop body`, `${pointer}/loop/carry/${source}`);
    }
  } else if (type === "subgraph") {
    for (const [name, value] of Object.entries(record(block.params))) expression(value, `${pointer}/subgraph/params/${name}`);
    const child = isRecord(block.inline)
      ? scopes.find((candidate) => candidate.pointer === `${pointer}/subgraph/inline`)
      : typeof block.use === "string"
        ? scopes.find((candidate) => candidate.pointer === `/subgraphs/${block.use}`)
        : undefined;
    if (child) for (const [name, value] of Object.entries(record(block.outputs_from))) {
      if (typeof value !== "string") continue;
      try {
        for (const reference of parseExpression(value).references) {
          if (reference[0] === "outputs" && reference[1] && !child.outputNames.has(reference[1])) add(findings, "AG203", "error", `undeclared subgraph output ${JSON.stringify(reference[1])}`, `${pointer}/subgraph/outputs_from/${name}`);
        }
      } catch (error) {
        add(findings, "AG204", "error", `invalid expression: ${(error as Error).message}`, `${pointer}/subgraph/outputs_from/${name}`);
      }
    }
  }
}

function checkScope(scope: Scope, document: JsonObject, findings: Finding[], scopes: Scope[]): void {
  const ids = Object.keys(scope.nodes);
  const idSet = new Set(ids);
  scope.effectiveEdges = effectiveEdges(scope.nodes, scope.edges);
  for (const [nodeId, node] of Object.entries(scope.nodes)) {
    for (const dependency of strings(node.depends_on)) {
      if (!idSet.has(dependency)) add(findings, "AG114", "error", `depends_on references unknown node ${JSON.stringify(dependency)}`, `${scope.pointer}/nodes/${nodeId}`);
    }
  }
  scope.edges.forEach((edge, index) => {
    const missing = [edge.from, edge.to].filter((id) => typeof id === "string" && !idSet.has(id));
    if (missing.length > 0) add(findings, "AG113", "error", `edge references unknown node(s) ${JSON.stringify(missing)}`, `${scope.pointer}/edges/${index}`);
  });
  const explicitPairs = new Set(scope.edges.map((edge) => `${String(edge.from)}\u0000${String(edge.to)}`));
  for (const [nodeId, node] of Object.entries(scope.nodes)) {
    for (const dependency of strings(node.depends_on)) {
      if (explicitPairs.has(`${dependency}\u0000${nodeId}`)) add(findings, "AG901", "warning", `${dependency} -> ${nodeId} declared by both depends_on and an explicit edge`, `${scope.pointer}/nodes/${nodeId}`);
    }
  }
  const validEdges = scope.effectiveEdges.filter((edge) => idSet.has(edge.from) && idSet.has(edge.to));
  const cycle = findCycle(ids, validEdges);
  if (cycle) add(findings, "AG111", "error", `cycle in effective edge set: ${cycle.join(" -> ")}`, scope.pointer);
  scope.predecessors = cycle ? new Map(ids.map((id) => [id, new Set<string>()])) : transitivePredecessors(ids, validEdges);

  const incoming = new Map(ids.map((id) => [id, 0]));
  const outgoing = new Map(ids.map((id) => [id, [] as string[]]));
  for (const edge of validEdges) {
    incoming.set(edge.to, (incoming.get(edge.to) ?? 0) + 1);
    outgoing.get(edge.from)?.push(edge.to);
    if (edge.when) validateExpression(edge.when, `${scope.pointer}/edges/${scope.edges.findIndex((candidate) => candidate.from === edge.from && candidate.to === edge.to)}/when`, findings, scope, edge.from, document);
  }
  for (const entrypoint of scope.entrypoints) {
    if (!idSet.has(entrypoint)) add(findings, scope.isRoot ? "AG115" : "AG133", "error", `entrypoint ${JSON.stringify(entrypoint)} is not a node in this scope`, scope.pointer);
    else if ((incoming.get(entrypoint) ?? 0) > 0) add(findings, "AG112", "error", `entrypoint ${JSON.stringify(entrypoint)} has incoming edges`, scope.pointer);
  }
  const reachable = new Set<string>();
  const stack = scope.entrypoints.filter((id) => idSet.has(id));
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || reachable.has(current)) continue;
    reachable.add(current);
    stack.push(...(outgoing.get(current) ?? []));
  }
  for (const nodeId of ids.filter((id) => !reachable.has(id)).sort()) {
    add(findings, "AG903", "warning", `node ${JSON.stringify(nodeId)} is unreachable from any entrypoint`, `${scope.pointer}/nodes/${nodeId}`);
  }

  for (const [nodeId, node] of Object.entries(scope.nodes)) {
    if (node.join === "n_of" && typeof node.join_count === "number" && node.join_count > (incoming.get(nodeId) ?? 0)) {
      add(findings, "AG116", "error", `join_count ${node.join_count} exceeds ${incoming.get(nodeId) ?? 0} incoming edges`, `${scope.pointer}/nodes/${nodeId}`);
    }
  }

  for (const [nodeId, node] of Object.entries(scope.nodes)) {
    const pointer = `${scope.pointer}/nodes/${nodeId}`;
    const type = typeof node.type === "string" ? node.type : "task";
    const outputs = records(node.outputs);
    if (nodeId === "self") add(findings, "AG117", "error", "'self' is a reserved namespace root and cannot be a node id", pointer);
    for (const other of ["loop", "map", "subgraph", "gate", "decision"]) {
      if (other in node && other !== type) add(findings, "AG101", "error", `node of type ${JSON.stringify(type)} declares a ${JSON.stringify(other)} block`, pointer);
    }
    if (type === "gate" && "intelligence" in node) add(findings, "AG102", "error", "gate nodes must not declare intelligence", pointer);
    if ((type === "decision" || type === "gate") && "decision" in outputs) add(findings, "AG122", "error", "'decision' is a reserved output name on decision and gate nodes", pointer);
    for (const [name, input] of Object.entries(records(node.inputs))) {
      const present = ["from", "template", "value"].filter((key) => key in input);
      if (present.length > 1) add(findings, "AG104", "error", `input ${JSON.stringify(name)} declares ${JSON.stringify(present)}; at most one is allowed`, `${pointer}/inputs/${name}`);
    }
    if (type === "decision") {
      const decision = record(node.decision);
      const branches = recordArray(decision.branches);
      const labels = branches.map((branch) => branch.label).filter((label): label is string => typeof label === "string");
      const duplicates = [...new Set(labels.filter((label, index) => labels.indexOf(label) !== index))].sort();
      if (duplicates.length > 0) add(findings, "AG124", "error", `duplicate branch labels ${JSON.stringify(duplicates)}`, pointer);
      if ((decision.evaluator ?? "agent") === "expression") branches.forEach((branch, index) => {
        if (!("when" in branch)) add(findings, "AG121", "error", `branch ${JSON.stringify(branch.label)} has no 'when' but evaluator is 'expression'`, `${pointer}/decision/branches/${index}`);
      });
      if (typeof decision.default_branch === "string" && !labels.includes(decision.default_branch)) add(findings, "AG123", "error", `default_branch ${JSON.stringify(decision.default_branch)} is not a declared label`, pointer);
    }
    const intelligence = record(node.intelligence);
    if (typeof intelligence.tier === "string" && typeof intelligence.level === "number" && TIER_LEVEL[intelligence.tier] !== intelligence.level) {
      add(findings, "AG141", "error", `tier ${JSON.stringify(intelligence.tier)} and level ${intelligence.level} disagree`, pointer);
    }
    if (typeof intelligence.tier === "string" && typeof intelligence.escalate_to === "string" && (TIER_LEVEL[intelligence.escalate_to] ?? 0) < (TIER_LEVEL[intelligence.tier] ?? 0)) {
      add(findings, "AG142", "error", `escalate_to ${JSON.stringify(intelligence.escalate_to)} is below tier ${JSON.stringify(intelligence.tier)}`, pointer);
    }
    if (intelligence.tier === "frontier" && !intelligence.rationale) add(findings, "AG905", "warning", "frontier-tier node has no rationale", pointer);
    if (["loop", "map", "subgraph"].includes(type)) {
      const block = record(node[type]);
      const use = block.use;
      if (typeof use === "string" && !record(document.subgraphs)[use]) add(findings, "AG132", "error", `${type}.use names unknown fragment ${JSON.stringify(use)}`, pointer);
      const ref = record(block.ref);
      if (typeof ref.uri === "string" && !ref.uri.startsWith(".") && !ref.uri.startsWith("/") && !("integrity" in ref)) add(findings, "AG909", "warning", `non-local subgraph reference ${JSON.stringify(ref.uri)} has no integrity digest`, pointer);
    }
    const failure = record(node.failure);
    recordArray(failure.fallback).forEach((step, index) => {
      const fallbackPointer = `${pointer}/failure/fallback/${index}`;
      if (step.strategy === "alternate_node" && typeof step.node === "string") {
        const alternate = scope.nodes[step.node];
        if (!alternate) add(findings, "AG113", "error", `fallback node ${JSON.stringify(step.node)} does not exist`, fallbackPointer);
        else {
          const required = Object.entries(outputs).filter(([, spec]) => spec.required !== false).map(([name]) => name);
          const missing = required.filter((name) => !declaredOutputs(alternate).has(name));
          if (missing.length > 0) add(findings, "AG151", "error", `fallback node ${JSON.stringify(step.node)} does not declare required outputs ${JSON.stringify(missing.sort())}`, fallbackPointer);
        }
      } else if (step.strategy === "relax_criteria") {
        const declared = new Set(recordArray(record(node.success).criteria).map((criterion) => criterion.id).filter((id): id is string => typeof id === "string"));
        const unknown = strings(step.criteria).filter((name) => !declared.has(name));
        if (unknown.length > 0) add(findings, "AG153", "error", `unknown criteria ${JSON.stringify(unknown.sort())}`, fallbackPointer);
      } else if (step.strategy === "degrade_outputs") {
        const unknown = strings(step.outputs).filter((name) => !(name in outputs));
        if (unknown.length > 0) add(findings, "AG153", "error", `unknown outputs ${JSON.stringify(unknown.sort())}`, fallbackPointer);
      }
    });
    if (typeof failure.compensation === "string") {
      const compensation = scope.nodes[failure.compensation];
      if (!compensation) add(findings, "AG113", "error", `compensation node ${JSON.stringify(failure.compensation)} does not exist`, pointer);
      else if (record(compensation.failure).compensation !== undefined) add(findings, "AG152", "error", `compensation node ${JSON.stringify(failure.compensation)} declares its own compensation`, pointer);
    }
    const escalation = record(failure.escalation);
    if (escalation.to === "node" && typeof escalation.node === "string" && !scope.nodes[escalation.node]) add(findings, "AG113", "error", `escalation node ${JSON.stringify(escalation.node)} does not exist`, pointer);
    const requirements = record(node.requirements);
    const mutating = requirements.workspace === "read_write" || strings(requirements.permissions).some((permission) => ["fs:write", "fs:delete", "git:commit", "git:push", "shell:exec"].some((prefix) => permission.startsWith(prefix)));
    if (mutating && !isRecord(node.success) && type === "task") add(findings, "AG902", "warning", "side-effecting node declares no success block", pointer);
    if (isRecord(node.success)) {
      const kinds = recordArray(node.success.criteria).filter((criterion) => (criterion.severity ?? "required") === "required").map((criterion) => criterion.kind).filter((kind): kind is string => typeof kind === "string");
      if (kinds.length > 0 && kinds.every((kind) => kind === "llm_judge" || kind === "human")) add(findings, "AG906", "warning", "success block has no deterministic required criterion", pointer);
    }
    const constraints = record(node.constraints);
    if (constraints.determinism === "strict" && !("seed" in constraints)) add(findings, "AG907", "warning", "determinism 'strict' without a seed", pointer);
    checkNodeExpressions(scope, nodeId, node, pointer, findings, document, scopes);
  }
}

export function validateGraph(document: JsonObject): ValidationReport {
  const findings: Finding[] = [];
  if (!validateSchema(document)) {
    for (const error of validateSchema.errors ?? []) {
      add(findings, schemaCode(error), "error", error.message ?? "schema validation failed", error.instancePath || "");
    }
  }
  const version = typeof document.ags_version === "string" ? /^(\d+)\.(\d+)$/.exec(document.ags_version) : null;
  if (!version) add(findings, "AG002", "error", `unparsable ags_version ${JSON.stringify(document.ags_version)}`);
  else if (version[1] !== "1" || Number(version[2]) > 0) add(findings, "AG002", "error", `unsupported AGS version ${document.ags_version}`);

  checkNamedRecursion(document, findings);
  const scopes = collectScopes(document);
  for (const scope of scopes) checkScope(scope, document, findings, scopes);
  const root = scopes[0];
  if (root) for (const [name, output] of Object.entries(records(document.outputs))) {
    if (typeof output.from === "string") validateExpression(output.from, `/outputs/${name}/from`, findings, root, undefined, document);
  }
  if (!("max_cost_usd" in record(document.constraints)) && !scopes.some((scope) => Object.values(scope.nodes).some((node) => isRecord(node.estimate)))) {
    add(findings, "AG908", "warning", "graph has neither constraints.max_cost_usd nor any node estimate; its cost cannot be previewed");
  }
  checkUnreadOutputs(scopes, document, findings);
  const errors = findings.filter((finding) => finding.severity === "error");
  const warnings = findings.filter((finding) => finding.severity === "warning");
  return { document, findings, errors, warnings, ok: errors.length === 0 };
}

export function validateValue(value: JsonValue): ValidationReport {
  if (value === null || Array.isArray(value) || typeof value !== "object") {
    const finding: Finding = { code: "AG001", severity: "error", message: "document root must be an object", pointer: "" };
    return { findings: [finding], errors: [finding], warnings: [], ok: false };
  }
  return validateGraph(value);
}

export { graphSchema };

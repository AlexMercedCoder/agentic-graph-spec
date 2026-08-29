package io.github.alexmercedcoder.ags;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Embedded-schema, semantic, topology, and AGX dataflow validation. */
public final class AgsValidator {
  private static final JsonSchema SCHEMA = loadSchema();
  private static final Set<String> EXPRESSION_KEYS = Set.of("from", "when", "expr", "target", "condition", "over");
  private static final Pattern EXTERNAL_OUTPUT = Pattern.compile("nodes\\.([A-Za-z_][\\w-]*)\\.outputs\\.([A-Za-z_][\\w-]*)");
  private static final Pattern OWN_OUTPUT = Pattern.compile("(?:self|nodes\\.self)\\.outputs\\.([A-Za-z_][\\w-]*)");

  private AgsValidator() {}

  private static JsonSchema loadSchema() {
    try (InputStream input = AgsValidator.class.getResourceAsStream("/schema/agentic-graph-1.0.schema.json")) {
      if (input == null) throw new IllegalStateException("embedded AGS schema is missing");
      JsonNode schema = JsonSupport.JSON.readTree(input);
      return JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012).getSchema(schema);
    } catch (IOException error) {
      throw new ExceptionInInitializerError(error);
    }
  }

  /** Validates an already parsed AGS document. */
  public static Ags.ValidationReport validate(ObjectNode document) {
    Report report = new Report(document);
    for (ValidationMessage message : SCHEMA.validate(document)) {
      String pointer = message.getInstanceLocation().toString();
      String type = message.getType();
      String code;
      if ("additionalProperties".equals(type)) code = "AG003";
      else if ("enum".equals(type) || "const".equals(type)) code = "AG004";
      else if (pointer.contains("/edges/") && "pattern".equals(type)) code = "AG103";
      else if (pointer.contains("/inputs/") && "pattern".equals(type)) code = "AG104";
      else code = "AG001";
      report.add(code, "error", message.getMessage(), pointer);
    }
    String version = document.path("ags_version").asText("");
    if (!version.matches("\\d+\\.\\d+") || !version.equals(Ags.SPEC_VERSION)) {
      report.add("AG002", "error", "unsupported or unparsable ags_version " + quoted(version), "");
    }
    if (report.errors.isEmpty()) semantic(document, report);
    return report.finish();
  }

  /** Loads and validates a path, returning parsing failures as diagnostics. */
  public static Ags.ValidationReport validate(Path path) {
    try {
      return validate(AgsParser.load(path));
    } catch (AgsParser.ParseException error) {
      Report report = new Report(null);
      report.add(error.code(), "error", error.getMessage(), "");
      return report.finish();
    }
  }

  private static final class Report {
    final ObjectNode document;
    final List<Ags.Finding> findings = new ArrayList<>();
    final List<Ags.Finding> errors = new ArrayList<>();
    final List<Ags.Finding> warnings = new ArrayList<>();
    Report(ObjectNode document) { this.document = document; }
    void add(String code, String severity, String message, String pointer) {
      Ags.Finding finding = new Ags.Finding(code, severity, message, pointer);
      findings.add(finding); if (severity.equals("error")) errors.add(finding); else warnings.add(finding);
    }
    Ags.ValidationReport finish() {
      return new Ags.ValidationReport(document, List.copyOf(findings), List.copyOf(errors), List.copyOf(warnings), errors.isEmpty());
    }
  }

  private record Edge(String from, String to) {}
  private record Scope(String pointer, ObjectNode nodes, List<JsonNode> edges, List<String> entrypoints, boolean root) {}

  private static void semantic(ObjectNode document, Report report) {
    List<Scope> scopes = scopes(document);
    scopes.forEach(scope -> validateScope(scope, document, report));
    validateRecursion(document, report);
    boolean estimate = scopes.stream().anyMatch(scope -> scope.nodes.properties().stream().anyMatch(entry -> entry.getValue().has("estimate")));
    if (!Ags.object(document.get("constraints")).has("max_cost_usd") && !estimate) {
      report.add("AG908", "warning", "graph has neither constraints.max_cost_usd nor any node estimate; its cost cannot be previewed", "");
    }
    checkUnreadOutputs(document, scopes, report);
  }

  private static List<Scope> scopes(ObjectNode document) {
    List<Scope> result = new ArrayList<>();
    Scope root = new Scope("", Ags.object(document.get("nodes")), array(document.get("edges")), JsonSupport.strings(document.get("entrypoints")), true);
    result.add(root); collectInline(root.nodes, "", result);
    Ags.object(document.get("subgraphs")).properties().forEach(entry -> {
      ObjectNode fragment = Ags.object(entry.getValue());
      String pointer = "/subgraphs/" + entry.getKey();
      Scope child = new Scope(pointer, Ags.object(fragment.get("nodes")), array(fragment.get("edges")), JsonSupport.strings(fragment.get("entrypoints")), false);
      collectInline(child.nodes, pointer, result); result.add(child);
    });
    return result;
  }

  private static void collectInline(ObjectNode nodes, String base, List<Scope> out) {
    nodes.properties().forEach(entry -> {
      ObjectNode node = Ags.object(entry.getValue()); String kind = node.path("type").asText("task");
      if (!Set.of("loop", "map", "subgraph").contains(kind)) return;
      String key = kind.equals("subgraph") ? "inline" : "body";
      JsonNode raw = Ags.object(node.get(kind)).get(key);
      if (raw == null || !raw.isObject()) return;
      ObjectNode fragment = (ObjectNode) raw; String pointer = base + "/nodes/" + entry.getKey() + "/" + kind + "/" + key;
      Scope child = new Scope(pointer, Ags.object(fragment.get("nodes")), array(fragment.get("edges")), JsonSupport.strings(fragment.get("entrypoints")), false);
      collectInline(child.nodes, pointer, out); out.add(child);
    });
  }

  private static List<JsonNode> array(JsonNode value) {
    List<JsonNode> out = new ArrayList<>(); if (value != null && value.isArray()) value.forEach(out::add); return out;
  }

  private static List<Edge> scopeEdges(Scope scope) {
    List<Edge> edges = new ArrayList<>();
    scope.nodes.properties().forEach(entry -> JsonSupport.strings(entry.getValue().get("depends_on")).forEach(parent -> edges.add(new Edge(parent, entry.getKey()))));
    scope.edges.forEach(raw -> { ObjectNode edge = Ags.object(raw); edges.add(new Edge(edge.path("from").asText(""), edge.path("to").asText(""))); });
    return edges;
  }

  private static void validateScope(Scope scope, ObjectNode document, Report report) {
    List<Edge> edges = scopeEdges(scope); Map<String, Integer> incoming = new HashMap<>(); Map<String, List<String>> direct = new HashMap<>();
    scope.nodes.properties().forEach(entry -> { incoming.put(entry.getKey(), 0); direct.put(entry.getKey(), new ArrayList<>()); });
    Set<Edge> explicit = new HashSet<>();
    scope.edges.forEach(raw -> { ObjectNode edge = Ags.object(raw); Edge pair = new Edge(edge.path("from").asText(""), edge.path("to").asText("")); explicit.add(pair);
      for (String id : List.of(pair.from, pair.to)) if (!scope.nodes.has(id)) report.add("AG113", "error", "edge references unknown node " + quoted(id), scope.pointer);
    });
    scope.nodes.properties().forEach(entry -> JsonSupport.strings(entry.getValue().get("depends_on")).forEach(parent -> {
      if (!scope.nodes.has(parent)) report.add("AG114", "error", "depends_on references unknown node " + quoted(parent), scope.pointer + "/nodes/" + entry.getKey());
      if (explicit.contains(new Edge(parent, entry.getKey()))) report.add("AG901", "warning", parent + " -> " + entry.getKey() + " declared by both depends_on and an explicit edge", scope.pointer + "/nodes/" + entry.getKey());
    }));
    for (Edge edge : edges) if (incoming.containsKey(edge.from) && incoming.containsKey(edge.to)) { incoming.merge(edge.to, 1, Integer::sum); direct.get(edge.to).add(edge.from); }
    if (hasCycle(scope.nodes, edges)) report.add("AG111", "error", "cycle in effective edge set", scope.pointer);
    for (String entry : scope.entrypoints) {
      if (!scope.nodes.has(entry)) report.add(scope.root ? "AG115" : "AG133", "error", "entrypoint " + quoted(entry) + " is not a node in this scope", scope.pointer);
      else if (incoming.get(entry) > 0) report.add("AG112", "error", "entrypoint " + quoted(entry) + " has incoming edges", scope.pointer);
    }
    Map<String, List<String>> outgoing = new HashMap<>(); edges.forEach(edge -> outgoing.computeIfAbsent(edge.from, ignored -> new ArrayList<>()).add(edge.to));
    Set<String> reachable = new HashSet<>(); ArrayDeque<String> queue = new ArrayDeque<>(scope.entrypoints);
    while (!queue.isEmpty()) { String id = queue.remove(); if (reachable.add(id)) queue.addAll(outgoing.getOrDefault(id, List.of())); }
    scope.nodes.properties().stream().map(Map.Entry::getKey).filter(id -> !reachable.contains(id)).sorted().forEach(id -> report.add("AG903", "warning", "node " + quoted(id) + " is unreachable from any entrypoint", scope.pointer + "/nodes/" + id));
    Map<String, Set<String>> predecessors = transitivePredecessors(scope.nodes, direct);
    scope.nodes.properties().stream().map(Map.Entry::getKey).sorted().forEach(id -> validateNode(scope, document, id, incoming.getOrDefault(id, 0), predecessors.get(id), report));
  }

  private static boolean hasCycle(ObjectNode nodes, List<Edge> edges) {
    Map<String, Integer> incoming = new HashMap<>(); Map<String, List<String>> outgoing = new HashMap<>();
    nodes.properties().forEach(entry -> incoming.put(entry.getKey(), 0));
    for (Edge edge : edges) if (incoming.containsKey(edge.from) && incoming.containsKey(edge.to)) { incoming.merge(edge.to, 1, Integer::sum); outgoing.computeIfAbsent(edge.from, ignored -> new ArrayList<>()).add(edge.to); }
    ArrayDeque<String> queue = new ArrayDeque<>(); incoming.forEach((id, count) -> { if (count == 0) queue.add(id); }); int seen = 0;
    while (!queue.isEmpty()) { String id = queue.remove(); seen++; for (String target : outgoing.getOrDefault(id, List.of())) if (incoming.merge(target, -1, Integer::sum) == 0) queue.add(target); }
    return seen != nodes.size();
  }

  private static Map<String, Set<String>> transitivePredecessors(ObjectNode nodes, Map<String, List<String>> direct) {
    Map<String, Set<String>> result = new HashMap<>();
    nodes.properties().forEach(entry -> { Set<String> seen = new HashSet<>(); ArrayDeque<String> stack = new ArrayDeque<>(direct.get(entry.getKey()));
      while (!stack.isEmpty()) { String parent = stack.removeLast(); if (seen.add(parent)) stack.addAll(direct.getOrDefault(parent, List.of())); } result.put(entry.getKey(), seen); });
    return result;
  }

  private static void validateNode(Scope scope, ObjectNode document, String id, int incoming, Set<String> predecessors, Report report) {
    ObjectNode node = Ags.object(scope.nodes.get(id)); String pointer = scope.pointer + "/nodes/" + id; String kind = node.path("type").asText("task");
    if (id.equals("self")) report.add("AG117", "error", "'self' is a reserved namespace root and cannot be a node id", pointer);
    for (String other : List.of("loop", "map", "subgraph", "gate", "decision")) if (!other.equals(kind) && node.has(other)) report.add("AG101", "error", "node of type " + quoted(kind) + " declares a " + quoted(other) + " block", pointer);
    if (kind.equals("gate") && node.has("intelligence")) report.add("AG102", "error", "gate nodes must not declare intelligence", pointer);
    if (Set.of("decision", "gate").contains(kind) && Ags.object(node.get("outputs")).has("decision")) report.add("AG122", "error", "'decision' is a reserved output name on decision and gate nodes", pointer);
    if (node.path("join").asText().equals("n_of") && node.path("join_count").asInt() > incoming) report.add("AG116", "error", "join_count exceeds incoming edges", pointer);
    ObjectNode intelligence = Ags.object(node.get("intelligence")); String tier = intelligence.path("tier").asText("");
    if (intelligence.has("level") && rank(tier) != intelligence.path("level").asInt()) report.add("AG141", "error", "intelligence tier and level disagree", pointer);
    if (intelligence.has("escalate_to") && rank(intelligence.path("escalate_to").asText()) < rank(tier)) report.add("AG142", "error", "escalate_to is below the configured tier", pointer);
    if (tier.equals("frontier") && intelligence.path("rationale").asText("").isEmpty()) report.add("AG905", "warning", "frontier-tier node has no rationale", pointer);
    if (Set.of("loop", "map", "subgraph").contains(kind)) {
      ObjectNode block = Ags.object(node.get(kind)); String used = block.path("use").asText("");
      if (!used.isEmpty() && !Ags.object(document.get("subgraphs")).has(used)) report.add("AG132", "error", kind + ".use names unknown fragment " + quoted(used), pointer);
      ObjectNode reference = Ags.object(block.get("ref")); String uri = reference.path("uri").asText("");
      if (!uri.isEmpty() && !uri.startsWith(".") && !uri.startsWith("/") && !reference.has("integrity")) report.add("AG909", "warning", "non-local subgraph reference has no integrity digest", pointer);
    }
    if (kind.equals("decision")) validateDecision(node, pointer, report);
    validateFailure(scope, node, pointer, report);
    ObjectNode requirements = Ags.object(node.get("requirements")); boolean mutating = requirements.path("workspace").asText().equals("read_write");
    for (String permission : JsonSupport.strings(requirements.get("permissions"))) for (String prefix : List.of("fs:write", "fs:delete", "git:commit", "git:push", "shell:exec")) mutating |= permission.startsWith(prefix);
    if (mutating && !node.has("success") && kind.equals("task")) report.add("AG902", "warning", "side-effecting node declares no success block", pointer);
    List<String> requiredKinds = new ArrayList<>(); JsonNode criteria = Ags.object(node.get("success")).get("criteria");
    if (criteria != null && criteria.isArray()) criteria.forEach(raw -> { ObjectNode criterion = Ags.object(raw); if (criterion.path("severity").asText("required").equals("required")) requiredKinds.add(criterion.path("kind").asText("")); });
    if (!requiredKinds.isEmpty() && requiredKinds.stream().allMatch(value -> value.equals("llm_judge") || value.equals("human"))) report.add("AG906", "warning", "success block has no deterministic required criterion", pointer);
    ObjectNode constraints = Ags.object(node.get("constraints")); if (constraints.path("determinism").asText().equals("strict") && !constraints.has("seed")) report.add("AG907", "warning", "determinism 'strict' without a seed", pointer);
    walkExpressions(node, pointer, "", scope, id, predecessors, report);
  }

  private static int rank(String tier) { return switch (tier) { case "minimal" -> 1; case "standard" -> 2; case "advanced" -> 3; case "frontier" -> 4; default -> 0; }; }

  private static void validateDecision(ObjectNode node, String pointer, Report report) {
    ObjectNode decision = Ags.object(node.get("decision")); Map<String, Integer> labels = new TreeMap<>(); JsonNode branches = decision.get("branches");
    if (branches != null && branches.isArray()) for (int index = 0; index < branches.size(); index++) { ObjectNode branch = Ags.object(branches.get(index)); String label = branch.path("label").asText(""); labels.merge(label, 1, Integer::sum);
      if (decision.path("evaluator").asText().equals("expression") && !branch.has("when")) report.add("AG121", "error", "branch " + quoted(label) + " has no 'when' but evaluator is 'expression'", pointer + "/decision/branches/" + index); }
    List<String> duplicates = labels.entrySet().stream().filter(entry -> entry.getValue() > 1).map(Map.Entry::getKey).toList();
    if (!duplicates.isEmpty()) report.add("AG124", "error", "duplicate branch labels " + duplicates, pointer);
    String fallback = decision.path("default_branch").asText(""); if (!fallback.isEmpty() && !labels.containsKey(fallback)) report.add("AG123", "error", "default_branch " + quoted(fallback) + " is not a declared label", pointer);
  }

  private static void validateFailure(Scope scope, ObjectNode node, String pointer, Report report) {
    ObjectNode failure = Ags.object(node.get("failure")); ObjectNode outputs = Ags.object(node.get("outputs")); JsonNode fallback = failure.get("fallback");
    if (fallback != null && fallback.isArray()) for (int index = 0; index < fallback.size(); index++) { ObjectNode step = Ags.object(fallback.get(index)); String location = pointer + "/failure/fallback/" + index;
      switch (step.path("strategy").asText("")) {
        case "alternate_node" -> { String target = step.path("node").asText(""); if (!scope.nodes.has(target)) report.add("AG113", "error", "fallback node " + quoted(target) + " does not exist", location); else {
          Set<String> available = declaredOutputs(Ags.object(scope.nodes.get(target))); List<String> missing = outputs.properties().stream().filter(entry -> entry.getValue().path("required").asBoolean(true) && !available.contains(entry.getKey())).map(Map.Entry::getKey).toList();
          if (!missing.isEmpty()) report.add("AG151", "error", "fallback node " + quoted(target) + " does not declare required outputs " + missing, location); } }
        case "relax_criteria" -> { Set<String> declared = new HashSet<>(); JsonNode criteria = Ags.object(node.get("success")).get("criteria"); if (criteria != null && criteria.isArray()) criteria.forEach(raw -> declared.add(raw.path("id").asText("")));
          List<String> unknown = JsonSupport.strings(step.get("criteria")).stream().filter(name -> !declared.contains(name)).toList(); if (!unknown.isEmpty()) report.add("AG153", "error", "unknown criteria " + unknown, location); }
        case "degrade_outputs" -> { List<String> unknown = JsonSupport.strings(step.get("outputs")).stream().filter(name -> !outputs.has(name)).toList(); if (!unknown.isEmpty()) report.add("AG153", "error", "unknown outputs " + unknown, location); }
        default -> { }
      }
    }
    String compensation = failure.path("compensation").asText(""); if (!compensation.isEmpty()) { if (!scope.nodes.has(compensation)) report.add("AG113", "error", "compensation node " + quoted(compensation) + " does not exist", pointer); else if (Ags.object(Ags.object(scope.nodes.get(compensation)).get("failure")).has("compensation")) report.add("AG152", "error", "compensation node " + quoted(compensation) + " declares its own compensation", pointer); }
    ObjectNode escalation = Ags.object(failure.get("escalation")); if (escalation.path("to").asText().equals("node")) { String target = escalation.path("node").asText(""); if (!scope.nodes.has(target)) report.add("AG113", "error", "escalation node " + quoted(target) + " does not exist", pointer); }
  }

  private static void walkExpressions(JsonNode value, String pointer, String key, Scope scope, String nodeId, Set<String> predecessors, Report report) {
    if (value.isObject()) value.properties().forEach(entry -> { if (!entry.getKey().equals("body") && !entry.getKey().equals("inline")) walkExpressions(entry.getValue(), pointer + "/" + entry.getKey(), entry.getKey(), scope, nodeId, predecessors, report); });
    else if (value.isArray()) for (int i = 0; i < value.size(); i++) walkExpressions(value.get(i), pointer + "/" + i, key, scope, nodeId, predecessors, report);
    else if (value.isTextual()) { String text = value.textValue(); if (EXPRESSION_KEYS.contains(key)) validateExpression(text, pointer, scope, nodeId, predecessors, report); else for (String inner : templateExpressions(text)) validateExpression(inner, pointer, scope, nodeId, predecessors, report); }
  }

  private static List<String> templateExpressions(String text) {
    List<String> values = new ArrayList<>(); int at = 0; while ((at = text.indexOf("${{", at)) >= 0) { int end = text.indexOf("}}", at + 3); if (end < 0) break; values.add(text.substring(at + 3, end).trim()); at = end + 2; } return values;
  }

  private static void validateExpression(String text, String pointer, Scope scope, String nodeId, Set<String> predecessors, Report report) {
    if (text.contains("${{")) { report.add("AG211", "error", "'${{ }}' interpolation used in expression position", pointer); return; }
    if (text.trim().isEmpty()) return; AgxParser.Expression parsed;
    try { parsed = AgxParser.parse(text); } catch (AgxParser.AgxException error) { report.add("AG204", "error", "invalid expression: " + error.getMessage(), pointer); return; }
    Map<String, int[]> functions = Map.ofEntries(
        Map.entry("get", new int[]{2, 3}), Map.entry("len", one()), Map.entry("count", one()), Map.entry("lower", one()), Map.entry("upper", one()), Map.entry("trim", one()), Map.entry("int", one()), Map.entry("float", one()), Map.entry("bool", one()), Map.entry("str", one()), Map.entry("json", one()), Map.entry("any", one()), Map.entry("all", one()), Map.entry("succeeded", one()), Map.entry("failed", one()), Map.entry("skipped", one()),
        Map.entry("contains", two()), Map.entry("startswith", two()), Map.entry("endswith", two()), Map.entry("matches", two()), Map.entry("split", two()), Map.entry("join", two()), Map.entry("default", two()), Map.entry("output", two()));
    for (AgxParser.Call call : parsed.calls()) { int[] allowed = functions.get(call.name()); if (allowed == null) report.add("AG204", "error", "unknown function " + quoted(call.name()), pointer); else if (call.arity() < allowed[0] || call.arity() > allowed[1]) report.add("AG204", "error", "function " + call.name() + " received " + call.arity() + " argument(s)", pointer); }
    for (List<String> parts : parsed.references()) { if (parts.isEmpty()) continue; if (parts.get(0).equals("secrets")) { report.add("AG205", "error", "expressions must not reference secrets.*", pointer); continue; }
      if (parts.get(0).equals("nodes") && parts.size() >= 2) { String target = parts.get(1); if (!scope.nodes.has(target)) { boolean childBound = pointer.contains("/loop/condition") || pointer.contains("/loop/collect/") || pointer.contains("/map/collect/"); if (!childBound) report.add(scope.root ? "AG203" : "AG202", "error", "unknown node " + quoted(target), pointer); }
        else if (parts.size() >= 4 && parts.get(2).equals("outputs") && !declaredOutputs(Ags.object(scope.nodes.get(target))).contains(parts.get(3))) report.add("AG206", "error", "node " + quoted(target) + " does not declare output " + quoted(parts.get(3)), pointer);
        else if (!target.equals(nodeId) && !predecessors.contains(target)) report.add("AG201", "error", "node " + quoted(nodeId) + " reads output of non-predecessor " + quoted(target), pointer); }
    }
  }

  private static int[] one() { return new int[]{1, 1}; }
  private static int[] two() { return new int[]{2, 2}; }

  private static Set<String> declaredOutputs(ObjectNode node) {
    Set<String> outputs = new TreeSet<>(); Ags.object(node.get("outputs")).properties().forEach(entry -> outputs.add(entry.getKey())); String kind = node.path("type").asText("task");
    if (kind.equals("decision") || kind.equals("gate")) outputs.add("decision"); ObjectNode block = Ags.object(node.get(kind));
    if (Set.of("gate", "loop", "map").contains(kind)) Ags.object(block.get("collect")).properties().forEach(entry -> outputs.add(entry.getKey()));
    if (kind.equals("subgraph")) Ags.object(block.get("outputs_from")).properties().forEach(entry -> outputs.add(entry.getKey())); return outputs;
  }

  private static void validateRecursion(ObjectNode document, Report report) {
    ObjectNode fragments = Ags.object(document.get("subgraphs")); Map<String, List<String>> dependencies = new HashMap<>();
    fragments.properties().forEach(fragment -> Ags.object(Ags.object(fragment.getValue()).get("nodes")).properties().forEach(entry -> { ObjectNode node = Ags.object(entry.getValue()); for (String kind : List.of("loop", "map", "subgraph")) { String used = Ags.object(node.get(kind)).path("use").asText(""); if (!used.isEmpty()) dependencies.computeIfAbsent(fragment.getKey(), ignored -> new ArrayList<>()).add(used); } }));
    Set<String> done = new HashSet<>(); for (String name : fragments.properties().stream().map(Map.Entry::getKey).toList()) visitFragment(name, dependencies, new ArrayList<>(), done, report);
  }

  private static void visitFragment(String name, Map<String, List<String>> dependencies, List<String> active, Set<String> done, Report report) {
    int at = active.indexOf(name); if (at >= 0) { List<String> cycle = new ArrayList<>(active.subList(at, active.size())); cycle.add(name); report.add("AG131", "error", "recursive subgraph reference: " + String.join(" -> ", cycle), "/subgraphs/" + name); return; }
    if (done.contains(name)) return; active.add(name); for (String next : dependencies.getOrDefault(name, List.of())) visitFragment(next, dependencies, active, done, report); active.remove(active.size() - 1); done.add(name);
  }

  private static void checkUnreadOutputs(ObjectNode document, List<Scope> scopes, Report report) {
    Set<String> reads = new HashSet<>(); walkStrings(document, text -> { Matcher matcher = EXTERNAL_OUTPUT.matcher(text); while (matcher.find()) reads.add(matcher.group(1) + "\u0000" + matcher.group(2)); });
    for (Scope scope : scopes) for (Map.Entry<String, JsonNode> entry : scope.nodes.properties()) { walkStrings(entry.getValue(), text -> { Matcher matcher = OWN_OUTPUT.matcher(text); while (matcher.find()) reads.add(entry.getKey() + "\u0000" + matcher.group(1)); });
      Ags.object(entry.getValue().get("outputs")).properties().forEach(output -> { if (!reads.contains(entry.getKey() + "\u0000" + output.getKey())) report.add("AG904", "warning", "output " + quoted(output.getKey()) + " of node " + quoted(entry.getKey()) + " is never read", scope.pointer + "/nodes/" + entry.getKey() + "/outputs/" + output.getKey()); }); }
  }

  private static void walkStrings(JsonNode value, java.util.function.Consumer<String> visitor) {
    if (value.isTextual()) visitor.accept(value.textValue()); else if (value.isContainerNode()) value.forEach(child -> walkStrings(child, visitor));
  }

  private static String quoted(String value) { return "\"" + value + "\""; }
}

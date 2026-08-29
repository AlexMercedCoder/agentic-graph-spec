package io.github.alexmercedcoder.ags;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Deterministic AGS conformance-level-0 graph planning helpers. */
public final class AgsPlanner {
  private AgsPlanner() {}

  /** Indicates that an effective graph cannot be topologically ordered. */
  public static final class CycleException extends Exception {
    private static final long serialVersionUID = 1L;
    CycleException() { super("graph contains a cycle"); }
  }

  /** Combines node dependencies and explicit edges into a normalized sorted edge set. */
  public static List<Ags.EffectiveEdge> effectiveEdges(ObjectNode document) {
    ObjectNode nodes = Ags.object(document.get("nodes"));
    Map<String, Ags.EffectiveEdge> unique = new TreeMap<>();
    nodes.properties().forEach(entry -> {
      for (String dependency : JsonSupport.strings(entry.getValue().get("depends_on"))) {
        Ags.EffectiveEdge edge = new Ags.EffectiveEdge(dependency, entry.getKey(), "sequence", null);
        unique.put(key(edge), edge);
      }
    });
    JsonNode edges = document.get("edges");
    if (edges != null && edges.isArray()) {
      edges.forEach(raw -> {
        ObjectNode edgeNode = Ags.object(raw);
        Ags.EffectiveEdge edge = new Ags.EffectiveEdge(
            edgeNode.path("from").asText(""), edgeNode.path("to").asText(""),
            edgeNode.path("kind").asText("sequence"),
            edgeNode.has("when") ? edgeNode.path("when").asText() : null);
        unique.putIfAbsent(key(edge), edge);
      });
    }
    return List.copyOf(unique.values());
  }

  private static String key(Ags.EffectiveEdge edge) {
    return edge.from() + "\u0000" + edge.to() + "\u0000" + edge.kind();
  }

  /** Returns a stable, identifier-tiebroken topological node order. */
  public static List<String> topologicalOrder(ObjectNode document) throws CycleException {
    ObjectNode nodes = Ags.object(document.get("nodes"));
    Map<String, Integer> incoming = new HashMap<>();
    Map<String, List<String>> outgoing = new HashMap<>();
    nodes.properties().forEach(entry -> { incoming.put(entry.getKey(), 0); outgoing.put(entry.getKey(), new ArrayList<>()); });
    for (Ags.EffectiveEdge edge : effectiveEdges(document)) {
      if (incoming.containsKey(edge.from()) && incoming.containsKey(edge.to())) {
        incoming.compute(edge.to(), (ignored, count) -> count + 1);
        outgoing.get(edge.from()).add(edge.to());
      }
    }
    outgoing.values().forEach(Collections::sort);
    PriorityQueue<String> ready = new PriorityQueue<>();
    incoming.forEach((id, count) -> { if (count == 0) ready.add(id); });
    List<String> order = new ArrayList<>();
    while (!ready.isEmpty()) {
      String id = ready.remove(); order.add(id);
      for (String target : outgoing.get(id)) {
        int count = incoming.compute(target, (ignored, value) -> value - 1);
        if (count == 0) ready.add(target);
      }
    }
    if (order.size() != nodes.size()) throw new CycleException();
    return List.copyOf(order);
  }

  /** Produces a deterministic, non-executing Level 0 graph plan. */
  public static Ags.GraphPlan plan(ObjectNode document) throws CycleException {
    ObjectNode nodes = Ags.object(document.get("nodes"));
    List<Ags.EffectiveEdge> edges = effectiveEdges(document);
    List<String> entrypoints = JsonSupport.strings(document.get("entrypoints"));
    Map<String, List<String>> outgoing = new HashMap<>();
    edges.forEach(edge -> outgoing.computeIfAbsent(edge.from(), ignored -> new ArrayList<>()).add(edge.to()));
    Set<String> reachable = new TreeSet<>();
    ArrayDeque<String> queue = new ArrayDeque<>(entrypoints);
    while (!queue.isEmpty()) {
      String id = queue.remove();
      if (reachable.add(id)) queue.addAll(outgoing.getOrDefault(id, List.of()));
    }
    List<String> unreachable = nodes.properties().stream().map(Map.Entry::getKey)
        .filter(id -> !reachable.contains(id)).sorted().toList();
    Map<String, Integer> histogram = new TreeMap<>();
    Set<String> unsupported = new TreeSet<>();
    long worstCase = 0;
    for (Map.Entry<String, JsonNode> entry : nodes.properties()) {
      ObjectNode node = Ags.object(entry.getValue());
      String kind = node.path("type").asText("task");
      String tier = Ags.object(node.get("intelligence")).path("tier").asText("none");
      histogram.merge(tier, 1, Integer::sum);
      long executions = 1;
      if (kind.equals("loop")) { executions = Ags.object(node.get("loop")).path("max_iterations").asLong(1); unsupported.add(kind); }
      if (kind.equals("map")) { executions = Ags.object(node.get("map")).path("max_items").asLong(1); unsupported.add(kind); }
      if (kind.equals("decision") || kind.equals("subgraph")) unsupported.add(kind);
      worstCase = Math.addExact(worstCase, executions);
    }
    return new Ags.GraphPlan(
        document.path("id").asText(""), AgsCanonical.graphDigest(document), topologicalOrder(document),
        List.copyOf(entrypoints), edges, List.copyOf(reachable), unreachable,
        Map.copyOf(histogram), worstCase, false, List.copyOf(unsupported));
  }
}

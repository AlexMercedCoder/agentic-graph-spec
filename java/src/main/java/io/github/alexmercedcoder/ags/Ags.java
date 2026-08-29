package io.github.alexmercedcoder.ags;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.List;
import java.util.Map;

/** Shared AGS constants and immutable result types. */
public final class Ags {
  /** AGS specification version implemented by this library. */
  public static final String SPEC_VERSION = "1.0";
  /** Java support-library version. */
  public static final String SUPPORT_VERSION = "1.0.3";

  private Ags() {}

  /** One machine-readable validation diagnostic. */
  public record Finding(String code, String severity, String message, String pointer) {}

  /** Complete parsing and validation result. */
  public record ValidationReport(
      ObjectNode document,
      List<Finding> findings,
      List<Finding> errors,
      List<Finding> warnings,
      boolean ok) {}

  /** Normalized dependency or explicitly declared graph edge. */
  public record EffectiveEdge(String from, String to, String kind, String when) {}

  /** Deterministic, non-executing conformance-level-0 graph plan. */
  public record GraphPlan(
      String graphId,
      String graphDigest,
      List<String> order,
      List<String> entrypoints,
      List<EffectiveEdge> effectiveEdges,
      List<String> reachable,
      List<String> unreachable,
      Map<String, Integer> tierHistogram,
      long worstCaseNodeExecutions,
      boolean executable,
      List<String> unsupportedFeatures) {}

  static ObjectNode object(JsonNode node) {
    return node != null && node.isObject() ? (ObjectNode) node : JsonSupport.emptyObject();
  }
}

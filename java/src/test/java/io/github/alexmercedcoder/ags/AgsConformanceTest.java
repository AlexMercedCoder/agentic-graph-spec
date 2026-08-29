package io.github.alexmercedcoder.ags;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

final class AgsConformanceTest {
  private static final Path ROOT = Path.of("..");

  @Test void acceptsSharedValidCorpus() {
    for (String name : List.of("minimal.agraph.yaml", "link-audit.agraph.yaml", "test-repair-loop.agraph.yaml",
        "docs-site-refresh.agraph.yaml", "library-v1-release.agraph.yaml", "library-v1-release.agraph.json")) {
      Ags.ValidationReport report = AgsValidator.validate(ROOT.resolve("examples").resolve(name));
      assertTrue(report.ok(), () -> name + ": " + report.errors());
    }
  }

  @Test void rejectsSharedInvalidCorpusWithExpectedCodes() {
    Map<String, String> expected = Map.of(
        "ag204-bad-expression.agraph.yaml", "AG204", "ag205-secret-reference.agraph.yaml", "AG205",
        "ag201-forward-read.agraph.yaml", "AG201", "ag113-unknown-node.agraph.yaml", "AG113",
        "ag141-tier-mismatch.agraph.yaml", "AG141", "ag111-cycle.agraph.yaml", "AG111",
        "ag131-recursive-subgraph.agraph.yaml", "AG131");
    expected.forEach((name, code) -> {
      Ags.ValidationReport report = AgsValidator.validate(ROOT.resolve("conformance/invalid").resolve(name));
      assertFalse(report.ok(), name);
      assertTrue(report.errors().stream().anyMatch(issue -> issue.code().equals(code)), () -> name + ": " + report.errors());
    });
  }

  @Test void canonicalIdentityMatchesOtherLibraries() throws Exception {
    ObjectNode graph = AgsParser.load(ROOT.resolve("examples/library-v1-release.agraph.yaml"));
    ObjectNode json = AgsParser.load(ROOT.resolve("examples/library-v1-release.agraph.json"));
    assertEquals(json, graph);
    assertEquals("sha256-ZaKZTS3i9OBDZNnKSNF2ZI22BZmOh1CcVNM0VZGDe+A=", AgsCanonical.graphDigest(graph));
  }

  @Test void strictParsingPlanningAndAgxArePortable() throws Exception {
    assertThrows(AgsParser.ParseException.class, () -> AgsParser.parse("ags_version: '1.0'\nid: one\nid: two\n", "yaml"));
    ObjectNode scalars = AgsParser.parse("ags_version: '1.0'\nid: demo\nentrypoints: [a]\nnodes:\n  a:\n    type: task\n    description: yes\n", "yaml");
    assertTrue(scalars.at("/nodes/a/description").isTextual());
    ObjectNode graph = AgsParser.load(ROOT.resolve("examples/minimal.agraph.yaml"));
    Ags.GraphPlan plan = AgsPlanner.plan(graph);
    assertEquals(List.of("draft_contributing", "maintainer_approval"), plan.order());
    assertFalse(plan.executable());
    AgxParser.Expression expression = AgxParser.parse("contains(nodes.draft.outputs.text, 'ok') && len(inputs.items) > 0");
    assertEquals(List.of("contains", "len"), expression.calls().stream().map(AgxParser.Call::name).toList());
  }
}

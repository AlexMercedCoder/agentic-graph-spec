#!/usr/bin/env python3
"""Behavioral tests for schema/agentic-graph-1.0.schema.json.

The schema encodes constraints that are easy to state in SPEC.md and easy to get
subtly wrong in JSON Schema -- conditional requirements, mutual exclusions, and
`additionalProperties` interacting with `allOf`. These tests assert the schema
actually accepts and rejects what the specification says it does.

Usage: python3 tools/test_schema.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "agentic-graph-1.0.schema.json"

BASE = {
    "ags_version": "1.0",
    "kind": "AgenticGraph",
    "id": "test/base",
    "title": "Base",
    "objective": "A minimal valid document to mutate.",
    "entrypoints": ["a"],
    "nodes": {
        "a": {"title": "A", "description": "Node A."},
        "b": {"title": "B", "description": "Node B."},
    },
}

FRAGMENT = {"entrypoints": ["x"], "nodes": {"x": {"title": "X", "description": "X."}}}


def mutate(**changes):
    doc = copy.deepcopy(BASE)
    doc.update(copy.deepcopy(changes))
    return doc


def node(node_id, **fields):
    doc = copy.deepcopy(BASE)
    doc["nodes"][node_id] = {"title": node_id.upper(), "description": "d", **copy.deepcopy(fields)}
    return doc


# (name, document, must_be_valid)  -- SPEC.md reference in the name
CASES: list[tuple[str, dict, bool]] = [
    ("SPEC 4: baseline document is valid", copy.deepcopy(BASE), True),

    # ---- edges, SPEC 8.2 ----
    ("8.2 sequence edge must not carry `when` (AG103)",
     mutate(edges=[{"from": "a", "to": "b", "when": "true"}]), False),
    ("8.2 conditional edge requires `when`",
     mutate(edges=[{"from": "a", "to": "b", "kind": "conditional"}]), False),
    ("8.2 conditional edge with `when` is valid",
     mutate(edges=[{"from": "a", "to": "b", "kind": "conditional", "when": "true"}]), True),
    ("8.2 on_failure edge may carry `when`",
     mutate(edges=[{"from": "a", "to": "b", "kind": "on_failure", "when": "true"}]), True),
    ("8.2 on_failure edge without `when` is valid",
     mutate(edges=[{"from": "a", "to": "b", "kind": "on_failure"}]), True),

    # ---- node types, SPEC 7 / AG101 / AG102 ----
    ("7.3 gate node must not declare intelligence (AG102)",
     node("a", type="gate", gate={"mode": "approve"}, intelligence={"tier": "standard"}), False),
    ("7.3 gate node without intelligence is valid",
     node("a", type="gate", gate={"mode": "approve"}), True),
    ("7.1 task node must not declare a loop block (AG101)",
     node("a", loop={"mode": "repeat", "max_iterations": 2, "body": FRAGMENT}), False),
    ("7.4 loop node requires a loop block",
     node("a", type="loop"), False),
    ("7.4 while loop requires a condition",
     node("a", type="loop", loop={"mode": "while", "max_iterations": 2, "body": FRAGMENT}), False),
    ("7.4 repeat loop needs no condition",
     node("a", type="loop", loop={"mode": "repeat", "max_iterations": 2, "body": FRAGMENT}), True),
    ("7.4 loop requires max_iterations",
     node("a", type="loop", loop={"mode": "repeat", "body": FRAGMENT}), False),
    ("7.4 loop must not declare both body and use",
     node("a", type="loop",
          loop={"mode": "repeat", "max_iterations": 2, "use": "f", "body": FRAGMENT}), False),
    ("7.5 map requires max_items",
     node("a", type="map", map={"over": "params.x", "as": "i", "body": FRAGMENT}), False),
    ("7.5 map with on_item_failure=threshold requires min_successes",
     node("a", type="map", map={"over": "params.x", "as": "i", "max_items": 5,
                                "on_item_failure": "threshold", "body": FRAGMENT}), False),
    ("7.6 subgraph requires one of use/inline/ref",
     node("a", type="subgraph", subgraph={"params": {}}), False),
    ("7.6 subgraph with ref is valid",
     node("a", type="subgraph", subgraph={"ref": {"uri": "./child.agraph.yaml"}}), True),
    ("7.2 decision node requires branches",
     node("a", type="decision", decision={"evaluator": "agent"}), False),
    ("7.2 decision branch requires a description",
     node("a", type="decision", decision={"branches": [{"label": "yes"}]}), False),

    # ---- joins, SPEC 6.1 ----
    ("6.1 join=n_of requires join_count", node("b", join="n_of"), False),
    ("6.1 join=n_of with join_count is valid", node("b", join="n_of", join_count=2), True),

    # ---- inputs and outputs, SPEC 9 ----
    ("9.2 input may not set both from and value (AG104)",
     node("b", inputs={"x": {"type": "string", "description": "d",
                             "from": "params.y", "value": 1}}), False),
    ("9.2 input with only `from` is valid",
     node("b", inputs={"x": {"type": "string", "description": "d", "from": "params.y"}}), True),
    ("9.2 input requires a description",
     node("b", inputs={"x": {"type": "string"}}), False),
    ("9.3 output requires a description",
     node("b", outputs={"x": {"type": "file"}}), False),

    # ---- success criteria, SPEC 10 ----
    ("10.2 command criterion requires `run`",
     node("b", success={"criteria": [{"id": "c", "kind": "command", "description": "d"}]}), False),
    ("10.2 file_exists criterion requires `path`",
     node("b", success={"criteria": [{"id": "c", "kind": "file_exists", "description": "d"}]}), False),
    ("10.2 json_schema criterion requires output plus a schema",
     node("b", success={"criteria": [{"id": "c", "kind": "json_schema",
                                      "description": "d", "output": "o"}]}), False),
    ("10.2 llm_judge criterion requires a rubric",
     node("b", success={"criteria": [{"id": "c", "kind": "llm_judge", "description": "d"}]}), False),
    ("10.2 every criterion requires a human-readable description",
     node("b", success={"criteria": [{"id": "c", "kind": "command", "run": "x"}]}), False),
    ("10.1 success mode=n_of requires count",
     node("b", success={"mode": "n_of",
                        "criteria": [{"id": "c", "kind": "command", "description": "d",
                                      "run": "x"}]}), False),
    ("10.1 success requires at least one criterion",
     node("b", success={"criteria": []}), False),

    # ---- intelligence, SPEC 11 ----
    ("11.1 tier must be one of the four named tiers",
     node("b", intelligence={"tier": "genius"}), False),
    ("11.1 level is bounded to 1-4",
     node("b", intelligence={"tier": "frontier", "level": 7}), False),
    ("11 intelligence requires a tier",
     node("b", intelligence={"hints": ["long_context"]}), False),
    ("11.3 unknown hints are rejected",
     node("b", intelligence={"tier": "standard", "hints": ["vibes"]}), False),

    # ---- requirements, SPEC 12 ----
    ("12 permission strings must match scope:action[:target]",
     node("b", requirements={"permissions": ["FS:WRITE"]}), False),
    ("12 well-formed permissions are accepted",
     node("b", requirements={"permissions": ["fs:write:src/**", "git:commit",
                                             "net:fetch:https://pypi.org"]}), True),
    ("12 tool requirement may be a string or an object",
     node("b", requirements={"tools": ["file_read", {"name": "test_runner", "optional": True}]}), True),

    # ---- failure handling, SPEC 14 ----
    ("14.2 fallback alternate_node requires `node`",
     node("b", failure={"fallback": [{"strategy": "alternate_node"}]}), False),
    ("14.2 fallback relax_criteria requires `criteria`",
     node("b", failure={"fallback": [{"strategy": "relax_criteria"}]}), False),
    ("14.2 escalation to a node requires `node`",
     node("b", failure={"escalation": {"to": "node"}}), False),
    ("14.2 escalation to human is valid on its own",
     node("b", failure={"escalation": {"to": "human", "roles": ["maintainer"]}}), True),

    # ---- human checkpoints, SPEC 15 ----
    ("15 checkpoint requires both `at` and `mode`",
     node("b", human=[{"at": "before_start"}]), False),
    ("15 unknown checkpoint stage is rejected",
     node("b", human=[{"at": "whenever", "mode": "approve"}]), False),

    # ---- document level ----
    ("3 ags_version must be 1.x", mutate(ags_version="2.0"), False),
    ("4 entrypoints must be non-empty", mutate(entrypoints=[]), False),
    ("4 nodes must be non-empty", mutate(nodes={}), False),
    ("5.1 kind must be AgenticGraph", mutate(kind="Workflow"), False),
    ("5.6 graph output requires `from`",
     mutate(outputs={"o": {"type": "file", "description": "d"}}), False),
    ("23 unknown top-level fields are rejected", mutate(bogus=1), False),
    ("23 x- extension fields are preserved and accepted",
     mutate(**{"x-acme-priority": "high"}), True),
    ("5.1 requires_conformance is bounded to 0-3", mutate(requires_conformance=9), False),
    ("Appendix B node ids are lowercase kebab/snake",
     {**copy.deepcopy(BASE), "nodes": {**BASE["nodes"], "Bad Id": {"title": "x", "description": "y"}}},
     False),
]


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    failures = 0
    for name, document, should_be_valid in CASES:
        errors = list(validator.iter_errors(document))
        is_valid = not errors
        if is_valid != should_be_valid:
            failures += 1
            want = "accept" if should_be_valid else "reject"
            print(f"  FAIL  {name}\n        expected the schema to {want} this document")
            if errors:
                print(f"        first error: {errors[0].message}")
        else:
            print(f"  ok    {name}")

    print(f"\n{len(CASES)} schema behavior cases, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

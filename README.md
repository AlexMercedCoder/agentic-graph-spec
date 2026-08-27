# Agentic Graph Specification (AGS)

**An open, implementation-neutral format for decomposing a project into a graph of agentic loops.**

Spec version `1.0` · maintenance release `1.0.1` · [SPEC.md](SPEC.md) · [JSON Schema](schema/agentic-graph-1.0.schema.json) · [Examples](examples/) · Apache-2.0

---

## What this is

An **Agentic Graph** is a directed acyclic graph where every node is a bounded *agentic loop* —
one unit of work an AI agent runs end to end — and every edge is a control-flow dependency.

A node is not a prompt and not a function call. It is a task with:

- a **precise brief** — what to accomplish, written so an agent that has seen nothing else can act on it;
- **typed inputs and outputs** — what it receives, what it must produce;
- **success conditions** — machine-checkable where possible, always human-readable, evaluated by the harness rather than asserted by the model;
- a **level of intelligence** — a normalized capability tier so a harness can route the work to an appropriately powerful model without the graph naming any model;
- **required tools, permissions and budgets** — the ceiling on what it may do and what it may spend;
- **failure handling** — retries with feedback, fallbacks, escalation, and human-in-the-loop checkpoints.

```
                    ┌──────────────────┐
                    │  audit_codebase  │  tier: standard
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │define_public_api │  tier: frontier
                    └────────┬─────────┘
                             ▼
                    ╔══════════════════╗
                    ║ api_design_review║  gate: human approval
                    ╚════════┬═════════╝
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
      ┌───────────────┐ ┌──────────┐ ┌──────────────┐
      │ implement_api │ │write_test│ │ write_docs   │   (parallel)
      └───────┬───────┘ └────┬─────┘ └──────┬───────┘
              └──────┬───────┘              │
                     ▼                      │
              ┌──────────────┐              │
              │verify_quality│              │
              └──────┬───────┘              │
                     └──────────┬───────────┘
                                ▼
                        ◆ release_readiness ◆   decision
                     ready ╱                ╲ needs work
                          ▼                  ▼
                 ┌────────────────┐  ┌────────────────┐
                 │prepare_release │◄─┤ remediate_gaps │
                 └───────┬────────┘  └────────────────┘
                         ▼
                 ╔════════════════╗
                 ║publish_approval║  gate
                 ╚═══════┬════════╝
                         ▼
                   ┌───────────┐
                   │  publish  │  human checkpoint before side effects
                   └───────────┘
```

That is [`examples/library-v1-release.agraph.yaml`](examples/library-v1-release.agraph.yaml),
byte-for-byte equivalent to [`examples/library-v1-release.agraph.json`](examples/library-v1-release.agraph.json).

## Why

Agent harnesses already decompose work. They do it *internally*: a planner emits some steps, the
steps live in the harness's own memory in the harness's own shape, and the plan disappears when
the session ends.

That has four consequences worth fixing:

1. **You cannot review the plan before paying for it.** By the time you see the decomposition, the
   tokens are spent.
2. **You cannot move it.** A decomposition produced by one harness is worthless to another.
3. **"Done" is whatever the model says.** Without declared acceptance criteria, completion is a
   claim, not a check.
4. **Every task gets the same model.** Without a declared capability demand, a harness either
   overspends on trivia or underspends on the one architectural decision that mattered.

AGS makes the decomposition a **first-class artifact**: written down, validated, reviewable,
diffable, portable, and executable by any conformant harness.

## Quickstart

### Read a graph

Start with [`examples/minimal.agraph.yaml`](examples/minimal.agraph.yaml) — two nodes, a gate, and
nothing else. Then read the canonical example above. Then read
[SPEC.md](SPEC.md) §5–§7.

### Write a graph

```yaml
ags_version: "1.0"
kind: AgenticGraph
id: myorg/add-healthcheck
title: Add a health check endpoint
objective: Expose GET /healthz returning service and dependency status.

entrypoints: [implement]

nodes:
  implement:
    title: Implement /healthz
    description: >
      Add a GET /healthz endpoint returning 200 with {"status":"ok"} when the database
      and cache are both reachable, and 503 with per-dependency detail when either is not.
    outputs:
      changed_files:
        type: file_set
        description: Source files added or modified.
    intelligence:
      tier: standard
      hints: [code_generation]
    requirements:
      tools: [file_read, file_write, shell_exec]
      permissions: [fs:read:**, fs:write:src/**, shell:exec:pytest*]
      workspace: read_write
    success:
      summary: The endpoint exists and behaves as specified under test.
      criteria:
        - id: tests_pass
          kind: command
          description: The health-check tests pass.
          run: pytest tests/test_healthz.py -q
```

### Validate it

```bash
python3 -m pip install jsonschema pyyaml
python3 tools/validate_agraph.py path/to/graph.agraph.yaml
python3 tools/validate_agraph.py --strict examples/     # advisories are failures
```

The validator implements all three layers described in [SPEC.md §18](SPEC.md#18-validation):
JSON Schema, cross-reference and topology checks, and AGX expression and dataflow analysis. It is a
reference implementation — SPEC.md is normative.

### Check the whole repo

```bash
tools/run_checks.sh
```

Four check groups: 55 schema behavior cases asserting the JSON Schema accepts and rejects exactly
what SPEC.md says it does; every example validating strictly; every fixture in
[`conformance/invalid/`](conformance/invalid/) producing the diagnostic it is named for; and the
JSON and YAML forms of the canonical example parsing to identical data.

## What is in this repository

| Path | What it is |
| --- | --- |
| [`SPEC.md`](SPEC.md) | The normative specification: data model, every field, execution semantics, validation catalogue, conformance levels, versioning policy, security considerations. |
| [`schema/agentic-graph-1.0.schema.json`](schema/agentic-graph-1.0.schema.json) | JSON Schema (draft 2020-12) for graph documents. The single source of truth for structure. |
| [`schema/agentic-graph-run-1.0.schema.json`](schema/agentic-graph-run-1.0.schema.json) | JSON Schema for run records — the portable account of one execution. |
| [`examples/`](examples/) | Five worked examples, including the canonical one in both JSON and YAML. |
| [`docs/expressions.md`](docs/expressions.md) | AGX, the small expression language used by conditions, bindings and criteria. |
| [`docs/harness-integration.md`](docs/harness-integration.md) | How a harness developer adds AGS support: parsing, validation, scheduling, model routing, criteria evaluation, HITL, run records. |
| [`docs/skill-authoring.md`](docs/skill-authoring.md) | How to package AGS support as an agent skill, so an agent can author and run graphs. |
| [`docs/design-rationale.md`](docs/design-rationale.md) | Why the format is shaped the way it is, and what was rejected. |
| [`GLOSSARY.md`](GLOSSARY.md) | Terms of art, defined once. |
| [`conformance/`](conformance/) | Fixtures a harness can test against. |
| [`tools/`](tools/) | Reference validator (`validate_agraph.py`, including an AGX parser), schema behavior tests (`test_schema.py`), and the repository self-check (`run_checks.sh`). |

### Examples

| Example | Demonstrates |
| --- | --- |
| [`minimal.agraph.yaml`](examples/minimal.agraph.yaml) | The smallest useful graph. Exactly the surface a conformance level 1 harness must support. |
| [`library-v1-release.agraph.yaml`](examples/library-v1-release.agraph.yaml) / [`.json`](examples/library-v1-release.agraph.json) | The canonical non-trivial decomposition, in both serializations. Parallel tracks, a decision, two gates, judged and machine-checked criteria, tiers from `minimal` to `frontier`, budgets, escalation. |
| [`test-repair-loop.agraph.yaml`](examples/test-repair-loop.agraph.yaml) | Bounded iteration: a `loop` node with an exit condition, `carry` between iterations, `collect` out, and escalating intelligence on retry. |
| [`docs-site-refresh.agraph.yaml`](examples/docs-site-refresh.agraph.yaml) | Composition: a `map` fan-out, a `subgraph` referencing another file, and a `subgraph` reusing a named local fragment. |
| [`link-audit.agraph.yaml`](examples/link-audit.agraph.yaml) | A reusable child graph, referenced by the one above. |

## Conformance levels

A harness does not have to implement everything to be useful. AGS defines four levels, and a graph
declares the one it needs with `requires_conformance`.

| Level | Name | Adds |
| --- | --- | --- |
| **0** | Reader | Parse JSON/YAML, validate, resolve dependencies, render a plan. No execution. |
| **1** | Minimal harness | Execute `task` and `gate` nodes, `sequence` edges, `join: all`, retries, `command`/`file_exists`/`artifact_present`/`human` criteria, intelligence-tier routing. |
| **2** | Standard harness | `decision` nodes, `conditional` and `on_failure` edges, all joins, the full expression language, budget enforcement, real parallelism, fallback and escalation, all HITL stages. |
| **3** | Full harness | `loop`, `map`, `subgraph`, `llm_judge` and `external` criteria, compensation, run records, checkpointing and resumption. |

A level 1 harness **rejects** a graph that needs more rather than silently ignoring what it cannot
do. See [SPEC.md §19](SPEC.md#19-conformance-levels).

## Design commitments

- **No vendor, model, or runtime is named anywhere in the normative model.** Capability demand is a
  tier; tools are logical capability names; the tier→model mapping is the harness's *routing
  profile* and is entirely its own business.
- **One data model, two serializations.** JSON and YAML are the same document. If a YAML file does
  not survive a lossless `yaml → json → yaml` round trip, it is not a valid AGS document.
- **Bounded by construction.** Every loop has a `max_iterations`. Every fan-out has a `max_items`.
  Every graph can carry a global execution ceiling. There is no way to write an unbounded document.
- **The graph is acyclic.** Iteration is a node that owns a body, not a back-edge. This keeps
  readiness, skip propagation and termination analysis tractable, and keeps every graph
  topologically sortable.
- **Control flow and data flow are separate.** Edges say what runs after what; `inputs.*.from` says
  what a node reads. Conflating them is the usual source of ambiguity in workflow formats.
- **Extensible without forking.** Every object accepts `x-` prefixed keys that harnesses must
  preserve and may ignore.

## Status and stability

AGS 1.0 is a **draft standard**. The data model is complete and self-consistent — spec, schema,
validator and examples are checked against each other by `tools/run_checks.sh` — but it has not yet
been through multiple independent implementations. Expect additive 1.x releases.

The [versioning policy](SPEC.md#21-versioning-and-compatibility) is normative: MINOR releases are
backward compatible, MAJOR releases get a new schema `$id`, and deprecated fields survive at least
one MINOR release before removal.

## Known implementations

- [Loro](https://github.com/alexmerced-oss/loro) implements graph validation, planning, execution, run records, gates, loops, maps, routing and resumption.
- [MagAgent](https://github.com/AlexMercedCoder/MagAgent) implements graph authoring, validation, scheduling, criteria, composition and run records.
- [Merced-AI](https://github.com/AlexMercedCoder/merced-ai) is tracked as an integration candidate and does not currently publish an AGS conformance level.

Implementation listings are evidence records, not endorsements. See [docs/implementation-report.md](docs/implementation-report.md); a conformance claim must identify the exact AGS maintenance release and fixture revision it passed.

## Contributing

Issues and pull requests are welcome, especially:

- **Implementation reports.** If you build a harness against this, say what was awkward.
- **Conformance fixtures.** New cases in `conformance/invalid/` with an `# EXPECT:` header.
- **Gaps.** A decomposition you cannot express is a spec bug, not a user error.

Anything that changes the data model must update, together: `SPEC.md`, the JSON Schema,
`tools/validate_agraph.py`, at least one example, and `CHANGELOG.md`. `tools/run_checks.sh` must
pass. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Code and schemas: [Apache License 2.0](LICENSE).

The specification text (`SPEC.md`, `GLOSSARY.md`, and the files under `docs/`) is additionally
available under [CC BY 4.0](LICENSE-CC-BY-4.0), so it can be quoted and adapted in other
specifications and documentation with attribution. Apache-2.0 was chosen for the repository as a
whole because it carries an explicit patent grant, which matters for a format people are expected to
implement.

# Agentic Graph Specification (AGS) — Version 1.0

**Status:** Draft standard
**Spec version:** `1.0`
**Document license:** Apache-2.0 (also available under CC BY 4.0 — see [LICENSE](LICENSE) and [LICENSE-CC-BY-4.0](LICENSE-CC-BY-4.0))
**Canonical schema:** [`schema/agentic-graph-1.0.schema.json`](schema/agentic-graph-1.0.schema.json)

---

## Table of contents

1. [Introduction](#1-introduction)
2. [Conventions](#2-conventions)
3. [Document format](#3-document-format)
4. [Document structure at a glance](#4-document-structure-at-a-glance)
5. [The Graph object](#5-the-graph-object)
6. [The Node object](#6-the-node-object)
7. [Node types](#7-node-types)
8. [Edges and the effective edge set](#8-edges-and-the-effective-edge-set)
9. [Data flow: inputs and outputs](#9-data-flow-inputs-and-outputs)
10. [Success conditions](#10-success-conditions)
11. [Intelligence tiers and model routing](#11-intelligence-tiers-and-model-routing)
12. [Requirements, tools and permissions](#12-requirements-tools-and-permissions)
13. [Constraints and budgets](#13-constraints-and-budgets)
14. [Failure handling](#14-failure-handling)
15. [Human in the loop](#15-human-in-the-loop)
16. [AGX: the expression language](#16-agx-the-expression-language)
17. [Execution semantics](#17-execution-semantics)
18. [Validation](#18-validation)
19. [Conformance levels](#19-conformance-levels)
20. [Run records](#20-run-records)
21. [Versioning and compatibility](#21-versioning-and-compatibility)
22. [Security considerations](#22-security-considerations)
23. [Extensibility](#23-extensibility)
24. [Appendix A — Defaults index](#appendix-a--defaults-index)
25. [Appendix B — Reserved names](#appendix-b--reserved-names)

---

## 1. Introduction

### 1.1 What an Agentic Graph is

An **Agentic Graph** is a portable, declarative decomposition of a project into a directed
acyclic graph of **agentic loops**. Each node describes one unit of work that an AI agent can
carry out end to end; each edge describes a control-flow dependency between units of work.

A node is not a prompt and not a function call. A node is a *bounded agentic loop*: an agent is
given a task description, a defined set of inputs, a declared set of tools and permissions, a
resource envelope, and an explicit definition of done. It iterates — reasoning, calling tools,
producing artifacts — until its success conditions are met or its budget is exhausted.

The spec exists so that the decomposition of a project is a **first-class, inspectable,
transferable artifact** rather than something implicit in a harness's internal planner. A graph
written for one harness should run on another; a graph produced by a planning agent should be
reviewable by a human before a single token is spent executing it.

### 1.2 Design goals

| Goal | How AGS addresses it |
| --- | --- |
| **Implementation neutral** | No vendor, model, provider, tool or runtime is named anywhere in the normative model. Capability demand is expressed as an abstract tier; tools are logical capability names. |
| **Format neutral** | One data model, expressible identically in JSON and YAML. The JSON Schema is the single source of truth. |
| **Reviewable before execution** | Every node states its task, its inputs, its outputs, its acceptance criteria and its cost envelope, so the whole plan can be read and approved up front. |
| **Machine-checkable completion** | Success is defined by criteria a harness can actually evaluate, not by a model asserting it is finished. |
| **Bounded by construction** | Every loop has a hard iteration ceiling, every fan-out has a hard width ceiling, and every graph can carry a global execution ceiling. There is no way to write an unbounded AGS document. |
| **Incrementally implementable** | Four conformance levels let a harness support the core today and grow into loops, maps and subgraphs later. |
| **Extensible without forking** | Every object accepts `x-` prefixed extension keys that harnesses must preserve. |

### 1.3 Non-goals

AGS deliberately does **not** specify:

- how an agent loop is implemented internally (prompting, tool-call protocol, context management);
- which models exist or what they are called;
- transport, storage, scheduling infrastructure, or an API for submitting graphs;
- a general-purpose workflow language. AGS is scoped to *agentic* work: tasks whose execution is
  open-ended and whose completion needs to be judged rather than merely returned.

### 1.4 Audience

- **Graph authors** (humans, and planning agents that generate graphs) — read §5–§16.
- **Harness developers** — read §17–§21, then [docs/harness-integration.md](docs/harness-integration.md).
- **Skill authors** packaging AGS support for an agent — read [docs/skill-authoring.md](docs/skill-authoring.md).

---

## 2. Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**,
**SHOULD NOT**, **RECOMMENDED**, **MAY** and **OPTIONAL** in this document are to be interpreted
as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174), when and only when they appear in all
capitals.

- **Harness** — the software that loads, validates, schedules and executes an Agentic Graph.
- **Author** — the human or agent that produced the graph document.
- **Run** — one execution of one graph document.
- **Scope** — the set of names visible to an expression at a point in the graph (§16.2).

Terms in *italics* on first use are defined in [GLOSSARY.md](GLOSSARY.md).

Field names in this specification are written in `snake_case`. This is normative: JSON member
names and YAML keys MUST match exactly, including case.

---

## 3. Document format

### 3.1 JSON and YAML equivalence

An AGS document is a single JSON value of type object. It MAY be serialized as:

- **JSON** — RFC 8259, UTF-8, no BOM. Recommended file extension `.agraph.json`.
- **YAML** — YAML 1.2 core schema, UTF-8. Recommended file extension `.agraph.yaml`.

A conformant harness MUST accept both and MUST treat them as the same document when they parse to
the same data. The YAML form MUST restrict itself to the subset of YAML 1.2 that maps onto the
JSON data model: no anchors resolving to non-JSON types, no custom tags, no non-string mapping
keys, no duplicate keys (a duplicate key is validation error `AG005`).

YAML anchors and aliases (`&name` / `*name`) MAY be used for authoring convenience. They are
resolved during parsing and are not part of the data model; a harness MUST NOT round-trip them.

> **Rule of thumb:** if a YAML document does not survive a lossless `yaml → json → yaml` round
> trip, it is not a valid AGS document.

### 3.2 Media types

| Form | Media type |
| --- | --- |
| JSON | `application/vnd.agentic-graph+json; version=1.0` |
| YAML | `application/vnd.agentic-graph+yaml; version=1.0` |
| Run record (JSON) | `application/vnd.agentic-graph-run+json; version=1.0` |

### 3.3 Canonical form and digests

The **canonical form** of a document is its JSON serialization with:

1. object members sorted by Unicode code point of the member name,
2. no insignificant whitespace,
3. UTF-8 encoding,
4. numbers serialized in the shortest round-trippable form.

`graph_digest` values and `subgraph.ref.integrity` values are `sha256-` followed by the
base64 encoding of the SHA-256 digest of the canonical form.

---

## 4. Document structure at a glance

```yaml
ags_version: "1.0"          # required — spec version
kind: AgenticGraph          # required — discriminator
id: acme/api-v2-release     # required — stable graph id
title: Ship API v2          # required
objective: |                # required — the one goal
  ...
requires_conformance: 2     # minimum harness level

params: {}                  # typed invocation surface
context: {}                 # shared background knowledge
attachments: []             # shared reference material
secrets: []                 # names only, never values

defaults: {}                # node-level defaults
entrypoints: [scope]        # required — where the run starts
nodes: {}                   # required — id -> node
edges: []                   # explicit control flow
subgraphs: {}               # named reusable fragments

constraints: {}             # global budgets
policy: {}                  # run-level behavior switches
outputs: {}                 # the graph's deliverables
success: {}                 # graph-level definition of done
metadata: {}
```

Two structural invariants hold for every valid document:

- **I1 — Node ids are unique.** `nodes` is a map keyed by node id, so uniqueness is guaranteed by
  the data model rather than by a separate check.
- **I2 — The graph is acyclic.** Iteration is expressed structurally by `loop` and `map` nodes,
  never by back-edges. See §7.4 for the rationale.

---

## 5. The Graph object

### 5.1 Identity and versioning fields

| Field | Type | Req. | Semantics |
| --- | --- | --- | --- |
| `ags_version` | string `^1\.[0-9]+$` | **yes** | Spec version the document targets. MAJOR.MINOR only; patch releases of the spec never change the data model. |
| `kind` | `"AgenticGraph"` | **yes** | Document discriminator. Reserved so future AGS document kinds can share the media type. |
| `id` | string | **yes** | Stable identifier for the graph *as a design*, not as a run. A slug (`api-v2-release`) or reverse-DNS/path form (`acme/api-v2-release`). Two documents with the same `id` are two versions of the same graph. |
| `title` | string | **yes** | Short human name, ≤200 chars. |
| `objective` | string | **yes** | The single goal the whole graph exists to accomplish, in one paragraph. If you cannot write this in one paragraph, you probably have two graphs. |
| `description` | string | no | Longer prose framing: background, scope boundaries, what is explicitly out of scope. |
| `version` | semver string | no | Author-controlled version of *this document*. Independent of `ags_version`. |
| `requires_conformance` | integer 0–3 | no (default `1`) | Minimum conformance level (§19) a harness needs. A harness below this level MUST refuse to execute the graph and MUST report which features it lacks. |
| `authors` | array of `{name, email?, url?, role?}` | no | Attribution. A harness that generates graphs SHOULD record itself here with `role: generator`. |
| `created_at`, `updated_at` | RFC 3339 date-time | no | Authoring timestamps. |
| `labels` | array of string | no | Free tags for catalogue/search. |
| `metadata` | object | no | Free-form, non-normative annotations. Never affects execution. |

### 5.2 Inputs to the graph

#### `params`

Map of parameter name → `param_spec`. This is the graph's **typed invocation surface**: the values
a caller supplies when starting a run.

```yaml
params:
  repo_url:
    type: string
    description: HTTPS URL of the repository to work in.
    required: true
  target_version:
    type: string
    description: Semantic version to release.
    default: "1.0.0"
```

`param_spec` fields: `type` (required, §9.1), `description` (required), `required`
(default `true`), `default`, `enum`, `schema` (inline JSON Schema), `example`.

A harness MUST reject a run whose supplied parameters do not satisfy the declared specs
(missing required parameter with no default → `AG301`; value failing `schema`/`enum` → `AG302`).

Parameters are readable as `params.<name>` everywhere in the graph.

#### `context`

Free-form object of shared, read-only background knowledge available as `context.<key>`. Unlike
`params`, context is authored into the document, not supplied at run time. Use it for style
guides, conventions, domain facts, and links every node may need.

```yaml
context:
  language: python
  style_guide: "Ruff defaults, line length 100, no bare excepts."
  team_conventions:
    review_required_for: ["src/auth/**"]
```

`context` values MUST be JSON values. A harness MUST NOT mutate `context` during a run.

#### `attachments`

Shared reference material a node may pull into its prompt. Each attachment has a `name` and
exactly one of `path` (workspace-relative), `uri`, or `inline`, plus optional `media_type` and
`description`. Nodes reference attachments by name in `inputs.*.from` as
`attachments.<name>`.

#### `secrets`

A list of `{name, description?, required?}`. **Only names appear in a graph document.** Secret
values are supplied out of band by the harness. Referencing `secrets.*` from an AGX expression is
validation error `AG205`; secrets reach a node only by being listed in
`node.requirements.secrets`, which instructs the harness to inject them into the node's execution
environment.

### 5.3 Structure fields

| Field | Type | Req. | Semantics |
| --- | --- | --- | --- |
| `entrypoints` | array of node id, ≥1 | **yes** | Nodes that become `ready` the moment the run starts. An entrypoint MUST have no incoming edges (`AG112`). |
| `nodes` | map id → Node | **yes** | The nodes. See §6. |
| `edges` | array of Edge | no | Explicit control flow. See §8. |
| `subgraphs` | map name → graph fragment | no | Named reusable fragments local to this document, referenced by `loop.use`, `map.use` and `subgraph.use`. |
| `defaults` | node defaults | no | Blocks shallow-merged into every node that omits them. See §6.3. |

### 5.4 `constraints` — global budgets

| Field | Type | Default | Semantics |
| --- | --- | --- | --- |
| `max_total_tokens` | integer | — | Total model tokens across the whole run, all nodes, all attempts. |
| `max_cost_usd` | number | — | Total estimated model spend for the run. |
| `max_wall_clock_seconds` | number | — | Total elapsed time from run start. |
| `max_parallel_nodes` | integer | `1` | Scheduler concurrency ceiling. `1` means fully sequential. |
| `max_node_executions` | integer | — | Runaway guard: total node executions including retries, loop iterations and map items. |
| `max_subgraph_depth` | integer | `5` | Maximum nesting depth of subgraph, loop and map scopes. |
| `deadline` | date-time | — | Absolute wall-clock deadline. |

When a global constraint is exceeded, the harness MUST stop scheduling new nodes, MUST let
currently running nodes reach a terminal state or be cancelled according to
`policy.on_node_failure`, and MUST finish the run with status `partial` (if any required output is
bound) or `failed`.

Node-level constraints (§13) are *nested* inside global ones: the effective limit for a node is
the minimum of its own limit and the run's remaining global budget.

### 5.5 `policy` — run-level behavior switches

| Field | Values | Default | Semantics |
| --- | --- | --- | --- |
| `on_expression_error` | `fail`, `false` | `fail` | `fail`: an AGX evaluation error is a run-fatal error. `false`: the expression yields `false`, a `warning` diagnostic is recorded, and the run continues. |
| `on_node_failure` | `halt`, `isolate`, `continue` | `isolate` | `halt`: first node failure ends the run. `isolate`: only the failed node's dependents are affected (normal skip propagation, §17.6). `continue`: dependents whose `join` can still be satisfied still run. |
| `on_unknown_field` | `error`, `warn` | `error` | Behavior when a non-`x-` field is not recognized by the harness. |
| `default_human_timeout_seconds` | number | — | Applied to any human checkpoint or gate that omits `timeout_seconds`. |
| `on_human_timeout` | `fail`, `hold`, `escalate`, `approve` | `hold` | Default applied to checkpoints that omit `on_timeout`. `approve` on timeout is dangerous and SHOULD be limited to `notify`-style checkpoints. |
| `checkpointing` | `none`, `per_node`, `continuous` | `per_node` | How often run state is persisted for resumption. |
| `resume` | `restart`, `resume_incomplete`, `resume_failed` | `resume_incomplete` | Behavior when a previously-checkpointed run is started again. |
| `record_run` | boolean | `true` | Emit a Run Record (§20). |

### 5.6 `outputs` — the graph's deliverables

Map of output name → `{type, description, from, required?, schema?, media_type?}`. `from` is an
AGX expression evaluated in the graph's final scope, normally referencing node outputs:

```yaml
outputs:
  release_notes:
    type: markdown
    description: Customer-facing notes for this release.
    from: nodes.write_release_notes.outputs.notes
```

If a `required` graph output cannot be bound when the run reaches its terminal state, the run
status is `partial` (not `succeeded`), and a diagnostic with code `RT041` is recorded.

### 5.7 `success` — the graph's definition of done

A `success_block` (§10) evaluated **after** every reachable node has reached a terminal state and
all graph outputs have been bound. Graph-level criteria are the place for end-to-end checks: the
full test suite, an integration smoke test, a final human sign-off.

A run is `succeeded` only if all of the following hold:

1. no required graph output is unbound;
2. `success` (if present) passes;
3. no node whose failure was not absorbed by a fallback/`on_exhausted` policy is in state `failed`.

---

## 6. The Node object

### 6.1 Common fields

Every node, of every type, accepts these fields.

| Field | Type | Req. | Semantics |
| --- | --- | --- | --- |
| `type` | enum | no (default `task`) | `task`, `decision`, `gate`, `loop`, `map`, `subgraph`. See §7. |
| `title` | string | **yes** | Short human name for the unit of work. |
| `description` | string | **yes** | **Precise statement of what the node must accomplish**, written as an instruction to the agent that will execute it. This is the primary carrier of intent — see §6.2. |
| `rationale` | string | no | Why this node exists in the decomposition. Aimed at human reviewers, not at the executing agent. |
| `instructions` | template | no | Longer-form guidance appended to `description` when the harness builds the node's prompt. May interpolate `${{ }}` expressions. |
| `labels` | array of string | no | Free tags. |
| `depends_on` | array of node id | no | Shorthand for a `sequence` edge from each listed node to this one (§8.2). |
| `join` | `all`, `any`, `n_of` | no (default `all`) | How multiple incoming edges combine into readiness (§17.5). |
| `join_count` | integer | conditional | Required when `join` is `n_of`. |
| `inputs` | map name → input spec | no | What the node receives (§9.2). |
| `outputs` | map name → output spec | no | What the node must produce (§9.3). |
| `success` | success block | no | Acceptance criteria (§10). |
| `intelligence` | intelligence block | no | Capability demand (§11). Forbidden on `gate` nodes. |
| `requirements` | requirements block | no | Tools, permissions, environment (§12). |
| `constraints` | constraints block | no | Resource envelope and determinism (§13). |
| `failure` | failure policy | no | Retries, fallback, escalation (§14). |
| `human` | array of human checkpoint | no | HITL checkpoints (§15). |
| `when` | expression | no | Node-level guard. Evaluated once at readiness; if false the node becomes `skipped` without running. |
| `estimate` | object | no | Non-binding planning estimates: `effort` (one of `xs`, `s`, `m`, `l`, `xl`), `tokens`, `cost_usd`, `wall_clock_seconds`. Used to preview a graph's cost to a human before running it. |
| `metadata` | object | no | Free-form. |

Type-specific blocks — `loop`, `map`, `subgraph`, `gate`, `decision` — are described in §7. Exactly
the block matching `type` may be present; any other type block is validation error `AG101`.

### 6.2 Writing a good `description`

`description` is the field that determines whether a node is executable by an agent that has never
seen the rest of the project. It is normatively REQUIRED and SHOULD:

- state the outcome, not the steps ("the CLI accepts `--format json` and emits schema-valid output"
  rather than "edit `cli.py`");
- name the artifacts it touches, since a harness may run the node in an isolated workspace;
- be self-contained given the node's declared `inputs` — an agent MUST NOT be expected to infer
  context that is not in `inputs`, `context`, or `attachments`;
- avoid restating `success` criteria; the criteria are the contract, the description is the brief.

### 6.3 `defaults` merging

`graph.defaults` may carry `intelligence`, `requirements`, `constraints`, `failure`, `human` and
`join`. Merge rules:

1. Merging is **per block, shallow, at the top level of the block**. If a node declares
   `constraints`, the node's `constraints` object is merged over the default `constraints` object
   key by key; keys the node does not mention are inherited.
2. Arrays are **replaced**, never concatenated. A node that declares `requirements.tools` replaces
   the default tool list entirely. (Rationale: silently unioning permissions is a security hazard.)
3. `human` is an array and therefore replaced wholesale.
4. `defaults` do not apply to fragment-scoped nodes unless the fragment declares its own
   `defaults`; a fragment's `defaults` apply only within that fragment. Parent defaults do **not**
   leak into loop/map/subgraph bodies. (Rationale: fragments must be relocatable.)

---

## 7. Node types

### 7.1 `task` — an agentic loop

The default and the workhorse. The harness gives an agent the node's brief, inputs, tools and
budget, and lets it iterate until it produces the declared outputs. The harness then evaluates
`success`.

```yaml
implement_pagination:
  type: task
  title: Implement cursor pagination on /v2/items
  description: >
    Add opaque cursor pagination to the GET /v2/items endpoint. Accept `limit`
    (1-200, default 50) and `cursor`; return `items` plus `next_cursor` (null on the
    last page). Cursors must be stable under concurrent inserts.
  depends_on: [design_api]
  inputs:
    design:
      type: markdown
      description: The approved API design document.
      from: nodes.design_api.outputs.design_doc
  outputs:
    changed_files:
      type: file_set
      description: Source files modified to implement pagination.
  intelligence:
    tier: advanced
    hints: [code_generation, precision_critical]
    rationale: Cursor stability under concurrency is easy to get subtly wrong.
  success:
    summary: Pagination works and is covered by tests.
    criteria:
      - id: tests_pass
        kind: command
        description: The pagination test module passes.
        run: pytest tests/test_pagination.py -q
```

Nothing in AGS constrains *how* the agent loops internally. The harness owns prompting, tool-call
format, context management and compaction.

### 7.2 `decision` — branch selection

A decision node selects exactly one **branch label** from an enumerated, mutually exclusive set.
The selected label is exposed as `nodes.<id>.outputs.decision` (a string) and is the usual subject
of outgoing `conditional` edges.

```yaml
triage:
  type: decision
  title: Decide the remediation path
  description: Classify the failure so the right remediation path runs.
  decision:
    question: "Given the failing test report, is this a product bug, a flaky test, or an environment problem?"
    evaluator: agent
    branches:
      - label: product_bug
        description: The implementation is wrong.
      - label: flaky_test
        description: The test is non-deterministic; the implementation is fine.
      - label: environment
        description: The failure is caused by the runtime environment, not the code.
    default_branch: product_bug
```

- `evaluator: agent` (default) — a model selects the label. The harness MUST constrain the model's
  answer to the declared labels; a response outside the set is a `criteria_failed`-class failure,
  unless `default_branch` is set, in which case the harness MUST use the default and record a
  `warning` diagnostic (`RT022`).
- `evaluator: expression` — no model call. The harness evaluates each branch's `when` in declared
  order and selects the first that is true; if none is true it uses `default_branch`, and if there
  is no default the node fails. Every branch MUST have `when` when `evaluator` is `expression`
  (`AG121`).

A decision node MAY also declare `outputs` beyond `decision` (for example a `reasoning` string).
`decision` is reserved and MUST NOT be declared in `outputs` (`AG122`).

Decision nodes MAY declare `intelligence`; classification under ambiguity is frequently a
`standard`-or-above task.

### 7.3 `gate` — human checkpoint

A gate is a node whose entire purpose is a human decision. It never calls a model, so
`intelligence` is forbidden on gates (`AG102`).

```yaml
approve_release:
  type: gate
  title: Release approval
  description: A release manager approves shipping v2 to production.
  depends_on: [run_integration_suite, write_release_notes]
  gate:
    mode: approve
    prompt: |
      Approve release ${{ params.target_version }}?
      Integration suite: ${{ nodes.run_integration_suite.outputs.summary }}
    roles: [release-manager]
    present:
      - nodes.write_release_notes.outputs.notes
    timeout_seconds: 86400
    on_timeout: hold
    on_reject: fail
```

`gate.mode`:

| Mode | Blocking | Semantics |
| --- | --- | --- |
| `approve` | yes | Binary approve/reject. Approval → node `succeeded`. Rejection → `gate.on_reject`. |
| `review` | yes | Approver may also edit the material shown. An edited value is written back to the node output whose name the reviewer's edit targets; the node MUST declare that output. Without edits, `review` behaves as `approve`. |
| `input` | yes | Approver supplies the values described in `gate.collect`; each becomes a node output. |
| `notify` | no | Fire-and-forget notification. The node succeeds immediately. |

`gate.on_reject`: `fail` (default), `skip_dependents` (node becomes `skipped`, propagating skips),
or `route` (node `succeeded`, with `outputs.decision` set to `rejected` so outgoing conditional
edges pick the path). With `route`, approval sets `outputs.decision` to `approved`.

### 7.4 `loop` — bounded iteration

**AGS graphs are acyclic.** Iteration is expressed by a `loop` node that owns a *body fragment*,
not by back-edges in the parent graph.

> **Rationale.** Cyclic graphs make readiness, skip propagation, budget attribution and static
> validation dramatically harder, and they make it impossible to guarantee termination by
> inspection. A body-owning loop node gives the same expressive power with a hard iteration
> ceiling that is visible in the document, and it keeps the parent graph topologically sortable.

```yaml
fix_until_green:
  type: loop
  title: Repair the test suite
  description: Iteratively diagnose and fix failures until the suite is green.
  loop:
    mode: until
    condition: nodes.run_tests.outputs.failing_count == 0
    max_iterations: 5
    on_max_iterations: escalate
    carry:
      diagnosis: previous_diagnosis      # body output -> next iteration's body input
    collect:
      final_report: nodes.run_tests.outputs.report
    body:
      entrypoints: [run_tests]
      params:
        previous_diagnosis:
          type: text
          description: Diagnosis from the previous iteration, empty on the first.
          required: false
          default: ""
      nodes:
        run_tests: { ... }
        diagnose:  { ... }
        apply_fix: { ... }
      edges:
        - { from: run_tests, to: diagnose, kind: conditional, when: nodes.run_tests.outputs.failing_count > 0 }
        - { from: diagnose, to: apply_fix }
```

| Field | Req. | Semantics |
| --- | --- | --- |
| `mode` | **yes** | `while`: evaluate `condition` **before** each iteration; stop when false. `until`: run an iteration, then evaluate `condition`; stop when true. `repeat`: run exactly `max_iterations` iterations. |
| `condition` | for `while`/`until` | AGX expression evaluated in the *body scope* of the most recent iteration (for `until`) or of the previous iteration (for `while`; on the first `while` test the body scope is empty, so the condition may only reference outer scope). |
| `max_iterations` | **yes** | Hard ceiling, 1–1000. There is no way to write an unbounded loop. |
| `on_max_iterations` | no (`fail`) | `fail`, `succeed` (accept the last iteration's state), or `escalate` (run `failure.escalation`). |
| `body` / `use` | exactly one | Inline graph fragment, or the name of a fragment in `graph.subgraphs`. |
| `carry` | no | Map of *body output name* → *body param name* fed into the next iteration. |
| `collect` | no | Map of *this node's output name* → AGX expression evaluated in the final iteration's body scope. |

Inside the body, `loop.index` (0-based), `loop.iteration` (1-based) and
`loop.previous.<output>` (the previous iteration's collected values, absent on iteration 0) are in
scope. An iteration that fails terminally ends the loop and the loop node fails, unless the body's
own `failure` policies absorb it.

### 7.5 `map` — bounded fan-out

A `map` node runs a body fragment once per element of a collection, optionally in parallel.

```yaml
review_each_module:
  type: map
  title: Review every changed module
  description: Run an independent review pass over each changed module.
  map:
    over: nodes.detect_changes.outputs.modules
    as: module
    max_items: 50
    on_over_limit: fail
    max_parallel: 4
    on_item_failure: threshold
    min_successes: 45
    collect:
      findings: nodes.review_module.outputs.findings
    body:
      entrypoints: [review_module]
      nodes:
        review_module: { ... }
```

| Field | Req. | Semantics |
| --- | --- | --- |
| `over` | **yes** | Expression producing an array. A non-array value is a runtime error (`RT025`). |
| `as` | **yes** | Binding name for the element inside the body scope. |
| `index_as` | no (`index`) | Binding name for the 0-based element index. |
| `max_items` | **yes** | Hard fan-out ceiling, 1–10000. |
| `on_over_limit` | no (`fail`) | `fail` if the collection is longer than `max_items`, or `truncate` (with a `warning` diagnostic). |
| `max_parallel` | no (`1`) | Per-node concurrency, further capped by `constraints.max_parallel_nodes`. |
| `on_item_failure` | no (`fail_fast`) | `fail_fast`: cancel siblings and fail. `continue`: record and carry on. `threshold`: succeed if at least `min_successes` items succeed. |
| `collect` | no | Map of *this node's output name* → expression evaluated per item. Results are gathered into an array **in input order**, regardless of completion order. Failed items contribute `null`. |

### 7.6 `subgraph` — composition

A `subgraph` node runs another graph as a single unit of work.

```yaml
publish_docs:
  type: subgraph
  title: Publish the documentation site
  description: Build, verify and publish docs using the shared docs-release graph.
  subgraph:
    ref:
      uri: ./graphs/docs-release.agraph.yaml
      expected_id: acme/docs-release
      integrity: sha256-Yl2X...
    params:
      site_root: context.docs_root
      version: params.target_version
    inherit_context: false
    outputs_from:
      site_url: outputs.published_url
```

Exactly one of `use` (a fragment in `graph.subgraphs`), `inline` (a fragment written in place), or
`ref` (another AGS document) MUST be present.

- **Isolation.** The child runs in a fresh scope. It sees only its own `params` (bound from
  `subgraph.params`, evaluated in the parent scope), its own `context`, and any entries in
  `subgraph.context`. Parent `context` is visible only when `inherit_context: true`.
- **Outputs.** `outputs_from` maps this node's output names to expressions evaluated in the child's
  final scope (typically `outputs.<name>`). Without `outputs_from`, the child's `outputs` map is
  copied verbatim onto the node's outputs.
- **Budgets.** The child's usage counts against the parent run's global constraints. A child's own
  `constraints` are clamped to the parent's remaining budget.
- **Recursion.** A graph MUST NOT reference itself transitively (`AG131`). Nesting depth is capped
  by `constraints.max_subgraph_depth`.
- **Integrity.** For a non-local `ref.uri`, a strict harness MUST require `integrity` and MUST
  refuse to load a document whose digest does not match (`RT051`). `expected_id`, when present,
  MUST match the child's `id` (`RT052`).
- **Conformance.** The child's `requires_conformance` MUST be satisfied by the executing harness.

---

## 8. Edges and the effective edge set

### 8.1 Edges are control flow only

AGS separates the two things graph formats usually conflate:

- **Edges carry control flow** — what runs after what, and under what condition.
- **`inputs.*.from` carries data flow** — which values a node reads.

A node MAY read the output of a node it has no edge from, provided that node is guaranteed to have
terminated first. The validator checks this: reading `nodes.X.outputs.*` when `X` is not a
transitive predecessor is validation error `AG201`.

### 8.2 Edge object

| Field | Type | Req. | Semantics |
| --- | --- | --- | --- |
| `from` | node id | **yes** | Source node, in the same scope. |
| `to` | node id | **yes** | Target node, in the same scope. |
| `kind` | `sequence`, `conditional`, `on_failure` | no (default `sequence`) | See below. |
| `when` | expression | conditional | REQUIRED for `conditional`. OPTIONAL for `on_failure`. FORBIDDEN for `sequence` (`AG103`). |
| `label` | string | no | Human-readable label, useful when rendering the graph. |
| `description` | string | no | Prose. |
| `carries` | array of name | no | Documentation-only hint listing which of `from`'s outputs `to` consumes. Not authoritative. |

**Edge kinds:**

- `sequence` — the plain dependency. Active when `from` reaches `succeeded`.
- `conditional` — active when `from` reaches `succeeded` **and** `when` evaluates true. Normatively
  equivalent to a `sequence` edge with a mandatory guard; it exists as a distinct kind so that
  branch structure is legible in the document and in rendered diagrams.
- `on_failure` — active when `from` reaches a terminal `failed` state, and `when` (if present) is
  true. This is the remediation path. `on_failure` edges are the only way a downstream node can run
  *because* something failed.

### 8.3 The effective edge set

The **effective edge set** `E` of a scope is:

```
E = dedupe( explicit_edges  ∪  { (from: d, to: n, kind: sequence) | n ∈ nodes, d ∈ n.depends_on } )
```

Deduplication key is the tuple `(from, to, kind, when)`; exact duplicates collapse silently.
Two edges with the same `(from, to)` but different `kind` or `when` are both retained and are both
evaluated — this is how a node can be reached either normally or via a remediation path.

`depends_on` is pure sugar. A document may use `depends_on` only, `edges` only, or both. Authors
SHOULD use `depends_on` for plain dependencies and `edges` for anything conditional; mixing the two
for the *same* pair of nodes is legal but discouraged (advisory `AG901`).

### 8.4 Acyclicity

The effective edge set of every scope MUST be acyclic (`AG111`). This is checked per scope: a loop
body's internal edges must themselves be acyclic, and the loop node in the parent graph is a single
vertex.

---

## 9. Data flow: inputs and outputs

### 9.1 Value types

`type` is a *logical* type, chosen to tell a harness how to marshal a value, not to be a full type
system.

| `type` | Meaning | Runtime representation |
| --- | --- | --- |
| `string` | Short scalar text | JSON string |
| `text` | Long unstructured prose | JSON string |
| `markdown` | Markdown-formatted prose | JSON string |
| `number`, `integer`, `boolean` | Scalars | JSON scalar |
| `object`, `array` | Structured data; constrain with `schema` | JSON object/array |
| `json` | Structured data of unspecified shape | any JSON |
| `file` | One file in the workspace | JSON string containing a workspace-relative path |
| `file_set` | Several files | JSON array of workspace-relative paths |
| `directory` | A directory in the workspace | JSON string path |
| `artifact` | A harness-managed artifact (document, dataset, build output) | harness-defined handle object with at least `{"id": string}` |
| `reference` | A pointer to an external resource | JSON string URI |
| `any` | Unconstrained | any JSON |

A harness MUST validate produced outputs against `type` (`RT031`) and, when present, against
`schema` (`RT032`).

### 9.2 `inputs`

Map of input name → input spec.

| Field | Req. | Semantics |
| --- | --- | --- |
| `type` | **yes** | §9.1. |
| `description` | **yes** | What this value is and how the node should use it. |
| `required` | no (`true`) | If true and the value resolves to absent with no `default`, the node fails with `output_missing`-class error before any model call (`RT033`). |
| `from` | no | AGX expression producing the value. |
| `template` | no | Interpolated text (`${{ }}`). |
| `value` | no | Literal value. |
| `default` | no | Used when the resolved value is absent and `required` is false. |
| `schema` | no | Inline JSON Schema. |
| `media_type` | no | Hint for file/artifact inputs. |
| `redact` | no (`false`) | The harness SHOULD omit this value from logs, traces and run records. |

At most one of `from`, `template`, `value` may be present (`AG104`). If none is present, the
harness resolves the input by name from the enclosing scope — first `params.<name>`, then
`context.<name>` — and otherwise treats it as absent. This *implicit binding* keeps simple graphs
short; explicit `from` is RECOMMENDED for anything non-obvious.

Inputs are resolved **once**, immediately before the first attempt of the node, and the resolved
values are reused verbatim by every retry of that node. This makes retries reproducible.

### 9.3 `outputs`

Map of output name → output spec: `type` (required), `description` (required), `required`
(default `true`), `path_hint`, `schema`, `media_type`, `redact`, `example`.

- A node cannot reach `succeeded` while any `required` output is unproduced (`RT033`).
- `path_hint` tells the agent where a file/artifact output is expected to live. It is advisory for
  the agent but a harness MAY use it to locate the artifact automatically.
- Outputs are readable downstream as `nodes.<id>.outputs.<name>`.

How an agent "returns" an output is harness-defined (a structured final message, a tool call, a
file at `path_hint`). What is normative is that the harness MUST populate the declared output names
before evaluating `success`.

---

## 10. Success conditions

### 10.1 The success block

```yaml
success:
  summary: The endpoint is implemented, tested, and documented.
  mode: all                # all | any | n_of
  count: 2                 # required when mode = n_of
  evaluation_order: cheapest_first
  criteria:
    - id: tests_pass
      kind: command
      description: The pagination test module passes with no failures.
      run: pytest tests/test_pagination.py -q
      expect_exit_code: 0
      timeout_seconds: 300
    - id: docs_updated
      kind: file_exists
      description: The endpoint reference page exists and is non-trivial.
      path: docs/api/items.md
      min_bytes: 500
    - id: design_respected
      kind: llm_judge
      description: The implementation matches the approved design.
      rubric: |
        Compare the implementation against the approved design document.
        Score 1.0 if every documented behavior is implemented as specified,
        0.5 if there are cosmetic deviations, 0.0 if behavior differs.
      inputs:
        - nodes.design_api.outputs.design_doc
        - nodes.implement_pagination.outputs.changed_files
      threshold: 0.8
      samples: 3
      judge_intelligence:
        tier: advanced
        hints: [adversarial_review, code_comprehension]
      severity: required
```

| Field | Req. | Semantics |
| --- | --- | --- |
| `summary` | no | One-sentence human definition of done. RECOMMENDED on every node. |
| `mode` | no (`all`) | How **required** criteria combine: `all`, `any`, or `n_of` with `count`. |
| `criteria` | **yes**, ≥1 | The criteria. |
| `evaluation_order` | no (`declared`) | `declared`: evaluate in order. `cheapest_first`: the harness MAY reorder to put cheap deterministic checks before expensive ones and short-circuit. Reordering MUST NOT change the pass/fail result. |

`severity: advisory` criteria are always evaluated (unless short-circuited) and always recorded, but
never affect the pass/fail outcome. Use them for signal you want in the run record without gating
progression.

### 10.2 Criterion kinds

Every criterion has `id`, `kind`, and a **required human-readable `description`**. The description
is not decoration: it is what a reviewer reads and what a harness shows a human at an escalation.

| `kind` | Required fields | Evaluation |
| --- | --- | --- |
| `command` | `run` | Execute `run` (optionally in `cwd`) with the node's permissions. Passes when the exit code equals `expect_exit_code` (default `0`) and, if `expect_stdout_matches` is set, stdout matches it. |
| `file_exists` | `path` | Passes when a workspace path or glob matches at least one file of at least `min_bytes` bytes. |
| `artifact_present` | `output` | Passes when the named declared output was produced and is non-empty. |
| `json_schema` | `output` + (`schema` or `schema_ref`) | Passes when the named output validates against the schema. |
| `regex` | `pattern` + (`output` or `target`) | Passes when `pattern` (with `flags`) matches the target text. `negate: true` inverts. |
| `expression` | `expr` | Passes when the AGX expression evaluates to boolean `true`. Non-boolean results are an evaluation error. |
| `llm_judge` | `rubric` | A model scores the material in `inputs` against `rubric`, returning a score in `[0,1]`. Passes when the score ≥ `threshold` (default `0.8`). With `samples > 1`, the **median** of independent judgements is used. `judge_intelligence` routes the judge. |
| `human` | `prompt` | A person confirms. Blocking. `roles` restricts who may sign off. |
| `external` | `check` | Delegates to a harness-registered checker with `params`. The escape hatch; using it makes a graph harness-specific, so it SHOULD be avoided in portable graphs. |

**`llm_judge` guidance.** A judge is a legitimate criterion for work whose quality is genuinely not
mechanically checkable (prose quality, design coherence, review thoroughness). It is *not* a
substitute for a test. Authors SHOULD pair every `llm_judge` criterion with at least one
deterministic criterion, and SHOULD set `samples: 3` for anything gating an expensive downstream
branch. A harness MUST NOT use the same model instance that produced the node's output as its own
judge within a single attempt without recording that fact in the run record.

### 10.3 How criteria gate progression

1. The node's agentic loop terminates and outputs are collected.
2. Required outputs are checked (`RT033`).
3. `success.criteria` are evaluated per `mode` and `evaluation_order`.
4. If the block passes, the node becomes `succeeded` and its outgoing edges resolve.
5. If it fails, the attempt outcome is `criteria_failed`, and §14 (retry → fallback → escalation →
   `on_exhausted`) applies. When `retry.feedback` is `failed_criteria` (the default), the harness
   MUST include each failed criterion's `description` and its recorded evidence in the next
   attempt's context. **This is the mechanism that makes retries productive rather than repetitive.**

A node with **no** `success` block succeeds when its agentic loop terminates normally and all
required outputs are present. Authors SHOULD supply a `success` block on every node that changes
state; advisory `AG902` flags side-effecting nodes without criteria.

---

## 11. Intelligence tiers and model routing

### 11.1 The scale

`intelligence.tier` is a **normalized, ordered capability demand**. It describes the task, not the
model. It exists so a harness can route work to an appropriately powerful model without the graph
naming any model.

| Tier | `level` | Use when the task is… | Typical work |
| --- | --- | --- | --- |
| `minimal` | 1 | Mechanical and verifiable at a glance. Correct behavior is fully determined by the instruction; mistakes are obvious and cheap. | Renaming, reformatting, templating, moving files, extracting a known field, running a fixed command and reporting the result. Often needs the smallest available model, sometimes no model at all. |
| `standard` | 2 | Ordinary single-domain work with clear instructions and a known-good pattern to follow. | Implementing a well-specified function, writing a documented test, drafting docs from a spec, routine refactors, summarization, straightforward tool sequences. |
| `advanced` | 3 | Multi-step reasoning, ambiguity resolution, or work that spans several files or systems within a frame that is already understood. | Non-obvious debugging, designing a module's interface, cross-cutting refactors, reconciling conflicting requirements, reviewing someone else's design. |
| `frontier` | 4 | Open-ended, novel, high-stakes, or adversarial — and a wrong answer is expensive *and* hard to detect. | System architecture, threat modelling, security review, choosing between strategies with long-lived consequences, research-grade synthesis, final gate reviews before irreversible actions. |

`level` is a numeric mirror provided so harnesses can compare tiers arithmetically. When both
`tier` and `level` are present they MUST agree (`AG141`).

### 11.2 Choosing a tier

A tier is not a quality dial — it is a statement about the *shape of the task*. Two questions
decide it:

1. **How much of the answer is determined by the instruction?** If the instruction fully determines
   it, you are at `minimal` or `standard`.
2. **How expensive is an undetected mistake?** If an error is cheap to catch (a test will fail), you
   can go a tier lower than instinct suggests. If it is silent and costly, go a tier higher.

Authors SHOULD supply `rationale` for any node at `advanced` or `frontier`; it is the field that
lets a reviewer challenge an expensive routing decision.

### 11.3 Hints

`hints` are unordered, advisory, and **never** substitute for the tier. A harness MAY use them to
choose among models that already satisfy the tier.

`reasoning_heavy`, `long_context`, `tool_use_heavy`, `code_generation`, `code_comprehension`,
`structured_output`, `creative`, `precision_critical`, `adversarial_review`, `multimodal`,
`multilingual`, `fast_iteration`, `low_cost`, `low_latency`.

### 11.4 Routing rules (normative)

Let `T` be the requested tier and `M` the tier of the model class the harness would use.

1. A harness MUST NOT route a node to a model class below `T` unless
   `intelligence.allow_downgrade` is `true`.
2. If it cannot satisfy `T` and `allow_downgrade` is `false`, the harness MUST fail the node with a
   `permission_denied`-class error and diagnostic `RT011`, before spending any tokens.
3. If `allow_downgrade` is `true`, the harness MAY route to the highest class it has and MUST record
   `routed.downgraded: true` with a reason in the run record.
4. A harness MAY route **up** freely (for example, if it only has one model).
5. `min_context_tokens` is a **hard** floor: routing to a model with a smaller usable context window
   is not permitted even when it satisfies the tier.
6. When `failure.retry.escalate_intelligence` is `true`, each retry routes at
   `intelligence.escalate_to` if set, otherwise one tier higher, clamped at `frontier`.
7. `intelligence` on a `gate` node is a validation error (`AG102`); gates never call models.

A harness's tier→model mapping is called its **routing profile** and is entirely
implementation-defined. Harnesses SHOULD document their profile and SHOULD expose it for
inspection, since it is the main thing that makes the same graph behave differently in two places.

---

## 12. Requirements, tools and permissions

```yaml
requirements:
  tools:
    - file_read
    - file_write
    - name: test_runner
      alternatives: [shell_exec]
      description: Something that can run the project's test suite.
    - name: web_search
      optional: true
  permissions:
    - fs:read:**
    - fs:write:src/**
    - shell:exec:pytest*
    - net:fetch:https://pypi.org
  mcp_servers: [github, filesystem]
  skills: [release-engineering]
  environment: [CI]
  secrets: [github_token]
  network: restricted
  workspace: read_write
```

- **`tools`** are *logical capability names*, not vendor tool names — `file_write`, not
  `str_replace_editor`. A harness maps them onto its own registry. An entry may be a plain string,
  or an object with `optional` and `alternatives`. A harness MUST refuse to start a node whose
  non-optional tools it cannot supply (`RT012`), and SHOULD substitute an `alternatives` entry
  before refusing.
- **`permissions`** use the form `scope:action[:target]` with scopes `fs`, `net`, `shell`, `git`,
  `process`, `secret`, `mcp`, `human`, `custom`. Targets are glob patterns for `fs`/`shell` and
  origins for `net`. Permissions are a **declared ceiling**: the harness's own policy always wins,
  and a harness MUST NOT grant a node more than its own policy permits regardless of what the graph
  asks for.
- **`mcp_servers`** names Model Context Protocol servers whose tools the node expects. Like `tools`,
  these are a request the harness may refuse; an unavailable server that the node needs makes the
  node `blocked` (`RT012`).
- **`skills`** names agent skills, playbooks or prompt bundles the harness should load for this node.
  Purely a hint about *how* to brief the agent; it never grants capability. A harness that does not
  recognize a skill name SHOULD warn and continue.
- **`environment`** lists environment variable names the node may read; only declared names are
  visible as `env.<name>`.
- **`secrets`** lists names from `graph.secrets` to inject into the node's execution environment.
- **`network`**: `none` (default), `restricted` (only origins implied by `net:` permissions), `full`.
- **`workspace`**: `none`, `read_only` (default), `read_write`.

Because `requirements` is a per-block replacement under `defaults` merging (§6.3), a node that
declares any `tools` replaces the default list entirely. This is deliberate: permissions and
capabilities should never widen by accident.

---

## 13. Constraints and budgets

| Field | Semantics |
| --- | --- |
| `max_input_tokens`, `max_output_tokens`, `max_total_tokens` | Token ceilings for the node, summed across all attempts unless the harness documents otherwise. |
| `max_cost_usd` | Estimated model spend ceiling for the node. |
| `max_wall_clock_seconds` | Elapsed-time ceiling for the node. |
| `max_tool_calls` | Tool invocation ceiling. |
| `max_agent_steps` | Maximum iterations of the agentic loop **inside** the node. This is the node's inner-loop bound, distinct from graph-level iteration. |
| `temperature`, `top_p`, `seed` | Sampling controls, passed through when the routed model supports them. |
| `determinism` | `strict`: same inputs must yield byte-identical outputs; implies `temperature: 0` and requires a `seed`, and a harness that cannot honor it MUST fail the node (`RT013`). `reproducible`: same inputs should yield equivalent outputs; the harness SHOULD pin sampling. `relaxed` (default): no guarantee. |
| `isolation` | `shared` (default), `worktree`, `sandbox`, `container`. A harness that cannot provide the requested isolation MUST fail the node rather than silently downgrading (`RT014`). |
| `concurrency_group` | Nodes sharing a group value never run concurrently, even when the scheduler has capacity. Use for nodes that touch the same mutable resource. |
| `deadline` | Absolute wall-clock deadline for the node. |

**Budget nesting.** The effective ceiling for a node is `min(node limit, remaining global limit)`.
Exceeding a node ceiling produces a `budget_exceeded`-class failure and enters §14. Exceeding a
global ceiling stops the run (§5.4).

---

## 14. Failure handling

### 14.1 Failure classes

Every unsuccessful attempt is classified. The class drives `retry.retry_on` matching, and it is
recorded in the run record.

| Class | Meaning |
| --- | --- |
| `transient` | Rate limit, network blip, temporary provider unavailability. |
| `model_error` | The model returned an unusable response (malformed structured output, refusal, empty). |
| `tool_error` | A tool invocation failed. |
| `timeout` | A node or criterion timeout elapsed. |
| `budget_exceeded` | A token, cost, tool-call or step ceiling was hit. |
| `criteria_failed` | The loop finished but `success` did not pass. |
| `output_missing` | A required input could not be resolved, or a required output was not produced. |
| `validation_error` | An output failed its `type` or `schema` check. |
| `permission_denied` | A required tool, permission, isolation mode or intelligence tier could not be supplied. |
| `any` | Matches every class. Use sparingly. |

### 14.2 The escalation ladder

A node that does not succeed walks this ladder in order. Each rung is optional; a node with no
`failure` block goes straight to `fail`.

```
attempt → retry (max_attempts) → fallback[0..n] → escalation → on_exhausted
```

**Retry** (`failure.retry`):

```yaml
failure:
  retry:
    max_attempts: 3            # total attempts including the first
    backoff: exponential       # none | fixed | linear | exponential
    initial_delay_seconds: 2
    max_delay_seconds: 60
    jitter: true
    retry_on: [transient, tool_error, criteria_failed]
    feedback: failed_criteria  # none | failure_summary | failed_criteria | full_transcript
    escalate_intelligence: true
```

An attempt is retried only if its failure class is listed in `retry_on`. Resolved inputs are reused
verbatim (§9.2), so the only things that change between attempts are the injected `feedback` and,
if `escalate_intelligence` is set, the routed tier.

**Fallback** (`failure.fallback`) — an ordered list tried after retries are exhausted. Each step has
a `strategy` and an optional `when` guard:

| Strategy | Effect |
| --- | --- |
| `alternate_node` | Run the node named in `node` in this node's place. Its outputs are adopted as this node's outputs (by name); the substitute node MUST declare compatible outputs (`AG151`). |
| `degrade_outputs` | Accept the node as succeeded with only the outputs listed in `outputs`; all other required outputs are demoted to optional for this run. |
| `relax_criteria` | Re-evaluate `success` with the criteria named in `criteria` demoted to `advisory`. |
| `human_takeover` | Hand the node to a person, who supplies the outputs directly. |
| `skip` | Mark the node `skipped` and continue; skip propagation (§17.6) applies. |

**Escalation** (`failure.escalation`) — notify or hand off:

| Field | Semantics |
| --- | --- |
| `to` | `human`, `node` (run the node named in `node`), `supervisor` (the harness's own planner/orchestrator), or `external`. |
| `node` | Required when `to` is `node`. |
| `roles` | Who should receive it, for `to: human`. |
| `channel` | Harness-defined notification channel identifier (a queue name, a chat channel, a webhook alias). Opaque to the spec; a harness that does not recognize it SHOULD fall back to its default channel and warn. |
| `message` | Template shown to the recipient. |
| `include` | What accompanies the escalation: any of `inputs`, `outputs`, `failed_criteria`, `transcript`, `diagnostics`. Defaults to `[failed_criteria, diagnostics]`. |

**`on_exhausted`** — the terminal disposition: `fail` (default), `skip`, `escalate`, or
`succeed_degraded` (the node is marked `succeeded` with whatever outputs exist; a `warning`
diagnostic `RT042` is recorded and the run's final status can be at best `partial`).

### 14.3 Compensation

`failure.compensation` names a node to run to **undo this node's side effects** when the run halts
after this node already succeeded. Compensation nodes run in reverse completion order of the
succeeded nodes that reference them, and only when the run terminates with status `failed` or
`cancelled`. A compensation node MUST NOT itself declare `compensation` (`AG152`). Compensation is
a conformance level 3 feature; a lower-level harness MUST report that it ignored the field.

---

## 15. Human in the loop

Two mechanisms, deliberately distinct:

- A **`gate` node** (§7.3) is a checkpoint that *is* a unit of work — a distinct box in the graph
  with its own dependencies. Use it for approvals that gate a phase.
- A **`human` checkpoint** on any node attaches a person to a moment in *that node's* lifecycle. Use
  it for review of one node's work.

```yaml
human:
  - id: pre_deploy
    at: before_side_effects
    mode: approve
    prompt: "About to write to production config. Proceed?"
    roles: [sre]
    timeout_seconds: 3600
    on_timeout: escalate
  - id: output_review
    at: after_outputs
    mode: review
    when: nodes.self.outputs.risk_score > 0.5
    prompt: "Review the generated migration before it is used downstream."
```

| `at` | Fires |
| --- | --- |
| `before_start` | After inputs resolve, before the first model call. |
| `before_side_effects` | Before the node's first externally-visible mutation (write, commit, network POST). The harness MUST support this by pausing at the first tool call the node's permissions classify as mutating. |
| `after_outputs` | After outputs are collected, before `success` is evaluated. |
| `on_criteria_failure` | After `success` fails, before retry. |
| `on_failure` | After the failure ladder reaches a terminal state. |
| `on_escalation` | When `failure.escalation` fires. |

`mode` matches gate modes (§7.3). `when` guards the checkpoint. `required: false` makes a
checkpoint advisory: the harness SHOULD surface it but MAY proceed without a response.

**Timeouts.** `timeout_seconds` falls back to `policy.default_human_timeout_seconds`; `on_timeout`
falls back to `policy.on_human_timeout` (default `hold`). `hold` leaves the node in
`awaiting_human` indefinitely — with `policy.checkpointing` set, the run can be safely suspended and
resumed later, which is the intended pattern for long approvals.

A harness at conformance level 1 that cannot present human checkpoints MUST NOT silently skip them:
it MUST fail the node with `permission_denied` and diagnostic `RT015`.

---

## 16. AGX: the expression language

AGX is a small, total, side-effect-free expression language. Full grammar and function reference:
[docs/expressions.md](docs/expressions.md). This section is normative summary.

### 16.1 Two syntactic positions

- **Expression position** — `when`, `condition`, `over`, `expr`, `from`, `outputs_from.*`,
  `subgraph.params.*`, `collect.*`. The *whole string* is an expression:
  `nodes.review.outputs.verdict == "approved"`.
- **Template position** — `description`-adjacent text fields (`instructions`, `prompt`, `message`,
  `rubric`, `template`). Expressions are interpolated with `${{ ... }}`; everything else is literal.

Mixing the two is an error: `${{ }}` in expression position is `AG211`.

### 16.2 Scopes and namespaces

| Namespace | Available | Contents |
| --- | --- | --- |
| `graph` | everywhere | `graph.id`, `graph.title`, `graph.objective`, `graph.version` |
| `params` | everywhere in its own graph | Declared parameters. |
| `context` | everywhere in its own graph | Declared context entries. |
| `attachments` | everywhere in its own graph | Declared attachments by name. |
| `nodes.<id>` | in the same scope | `.status`, `.outputs.<name>`, `.attempts`, `.duration_seconds`, `.decision` (decision/gate nodes). |
| `self` | within a node | `self.id`, `self.attempt` (1-based), `self.inputs.<name>`, and inside `after_outputs`/criteria, `self.outputs.<name>`. Node-scoped `human.when` and `success` criteria use `nodes.self.outputs.*` as an alias of `self.outputs.*`. |
| `loop` | inside a loop body | `loop.index` (0-based), `loop.iteration` (1-based), `loop.previous.<collected output>`. |
| `<as>` / `<index_as>` | inside a map body | The current element and its index, under the names given by `map.as` / `map.index_as`. |
| `outputs` | in `subgraph.outputs_from` and graph `success` | The graph's bound outputs. |
| `env` | within a node | Only variables declared in `requirements.environment`. |
| `secrets` | **never** | Referencing `secrets.*` is `AG205`. |

Nodes inside a fragment cannot see the parent scope's `nodes.*` (`AG202`). Everything a fragment
needs must arrive through `params`.

### 16.3 Operators, literals and functions

- Literals: strings (single or double quoted), numbers, `true`, `false`, `null`, array literals
  `[a, b]`.
- Operators (highest precedence first): `()` · `!` unary `-` · `* /  %` · `+ -` · `< <= > >=` ·
  `== !=` · `in` · `&&` / `and` · `||` / `or`.
- Comparison is **strictly typed**: comparing a string to a number is an evaluation error, not
  `false`. `==` on objects and arrays is deep equality.
- Functions (all pure and total): `len(x)`, `count(x)`, `contains(haystack, needle)`,
  `startswith(s, p)`, `endswith(s, p)`, `lower(s)`, `upper(s)`, `trim(s)`, `matches(s, pattern)`,
  `split(s, sep)`, `join(list, sep)`, `int(x)`, `float(x)`, `bool(x)`, `str(x)`, `json(s)`,
  `get(obj, path, default)`, `default(x, fallback)`, `any(list)`, `all(list)`,
  `succeeded(node_id)`, `failed(node_id)`, `skipped(node_id)`, `output(node_id, name)`.
- There are no user-defined functions, no assignment, no loops, no I/O, and nothing
  time-dependent — `now()` deliberately does not exist, because expressions must be replayable.

### 16.4 Evaluation errors

Referencing an unknown name, calling a function with wrong arity or types, or comparing
incompatible types is an **evaluation error**, handled per `policy.on_expression_error` (§5.5).
Referencing a node that has not yet reached a terminal state is a validation error at load time
(`AG201`), not a runtime error.

---

## 17. Execution semantics

This section defines what it means for a harness to "evoke" a graph. A harness MUST produce results
consistent with this model; it need not be structured this way internally.

### 17.1 Phases

```
LOAD → VALIDATE → PLAN → INITIALIZE → SCHEDULE ⇄ EXECUTE → FINALIZE
```

**LOAD.** Parse JSON or YAML into the data model. Reject duplicate keys, non-JSON YAML constructs,
and `ags_version` values the harness does not support (§21).

**VALIDATE.** Run the full rule catalogue in §18. A harness MUST NOT execute any node of a document
with unresolved `error`-severity findings.

**PLAN.** Compute, for every scope: the effective edge set (§8.3), a topological order, the set of
reachable nodes, and — using `estimate` when present — a projected cost. A harness SHOULD be able to
render this plan to a human **without executing anything**; `requires_conformance: 0` harnesses do
exactly this and stop.

**INITIALIZE.** Bind and validate `params`. Freeze `context` and `attachments`. Set every node to
`pending`, then set the `entrypoints` to `ready`. Verify that global constraints are non-zero and
that the routing profile can satisfy every declared `intelligence.tier` in the graph — failing fast
here is strongly RECOMMENDED over discovering it mid-run.

**SCHEDULE ⇄ EXECUTE.** The loop in §17.4.

**FINALIZE.** Bind graph `outputs`, evaluate graph `success`, run any pending compensation, compute
the final status, emit the run record.

### 17.2 Node states

```
pending ──► ready ──► running ──► succeeded
   │          │          │   │
   │          │          │   └──► awaiting_human ──► running
   │          │          └──────► failed
   └──────────┴─────────────────► skipped
                                  cancelled
                                  blocked
```

| State | Meaning |
| --- | --- |
| `pending` | Not yet eligible; some incoming edges unresolved. |
| `ready` | Join predicate satisfied and `when` (if any) true; awaiting a scheduler slot. |
| `running` | Executing an attempt. |
| `awaiting_human` | Paused at a human checkpoint or gate. |
| `succeeded` | Terminal. Required outputs present and `success` passed. |
| `failed` | Terminal. Failure ladder exhausted with `on_exhausted: fail`. |
| `skipped` | Terminal. Join predicate became unsatisfiable, `when` was false, or a policy skipped it. |
| `cancelled` | Terminal. Stopped by budget exhaustion, `fail_fast`, or operator action. |
| `blocked` | Terminal. Could not start because a requirement (tool, permission, tier, isolation) was unavailable. Treated as `failed` for edge resolution. |

`succeeded`, `failed`, `skipped`, `cancelled` and `blocked` are the **terminal** states.

### 17.3 Edge activation

When node `S` reaches a terminal state, each outgoing edge `e = (S → T, kind, when)` resolves to
`active` or `inactive`:

| `S` terminal state | `kind: sequence` | `kind: conditional` | `kind: on_failure` |
| --- | --- | --- | --- |
| `succeeded` | **active** | active iff `when` is true | inactive |
| `failed` / `blocked` | inactive | inactive | active iff `when` absent or true |
| `skipped` | inactive | inactive | inactive |
| `cancelled` | inactive | inactive | inactive |

**Skip propagation** falls out of the last two rows: a skipped or cancelled node makes all of its
outgoing edges inactive, so its dependents' joins become unsatisfiable and they too become
`skipped`.

### 17.4 The scheduling loop

```
while there exists a node in {ready, running, awaiting_human}:
    resolve all newly-terminal nodes' outgoing edges          (§17.3)
    recompute readiness for every pending node                (§17.5)
    mark newly-unsatisfiable pending nodes as skipped         (§17.6)
    while capacity remains and a ready node exists:
        pick a ready node respecting max_parallel_nodes,
             constraints.concurrency_group, and — as a tiebreak —
             topological order then declaration order
        execute it                                            (§17.7)
```

**Determinism of scheduling.** When two nodes are simultaneously ready and both fit in the
concurrency budget, a harness MUST pick between them by topological order, breaking ties by
declaration order in the document. This makes sequential execution of the same graph reproducible
across harnesses.

**Parallelism.** With `max_parallel_nodes: 1`, execution is a deterministic sequence. Above 1, nodes
that are simultaneously ready and not in a shared `concurrency_group` MAY run concurrently. Nodes
that write to the same files SHOULD share a `concurrency_group` or request `isolation: worktree`.

### 17.5 Readiness

For node `N` with incoming effective edges `I(N)`:

- If `I(N)` is empty: `N` is `ready` at run start if `N ∈ entrypoints`, and otherwise unreachable
  (advisory `AG903`) and never runs.
- Otherwise, let `A` = active edges in `I(N)`, `R` = resolved edges in `I(N)`. `N` becomes `ready`
  when:

| `join` | Ready when |
| --- | --- |
| `all` (default) | `R = I(N)` and `A = I(N)` — every incoming edge resolved and active. |
| `any` | `\|A\| ≥ 1` — fires as soon as the *first* incoming edge goes active, without waiting for the rest. |
| `n_of` | `\|A\| ≥ join_count`. |

and, additionally, `N.when` (if present) evaluates true.

With `join: any` or `n_of`, edges that resolve *after* the node has already started are recorded in
the run record but do not re-trigger the node. A node executes at most once per scope instance
(loop iterations and map items each create a fresh scope instance).

### 17.6 Skipping

`N` becomes `skipped` when its join predicate can no longer be satisfied:

| `join` | Unsatisfiable when |
| --- | --- |
| `all` | any incoming edge resolves `inactive`. |
| `any` | every incoming edge is resolved and all are `inactive`. |
| `n_of` | `\|A\| + \|unresolved\| < join_count`. |

or when `N.when` is present and false, or when a policy (`fallback: skip`, `on_exhausted: skip`,
`gate.on_reject: skip_dependents`) skips it.

`policy.on_node_failure: continue` modifies §17.6 only: a node whose *only* unsatisfiable reason is
an upstream `failed` node is still attempted if its join could otherwise be met. Inputs that cannot
resolve then fail the node normally.

### 17.7 Executing one node

```
1.  Resolve inputs                        (§9.2)  → output_missing on failure
2.  Verify requirements: tools, permissions, isolation, tier   → blocked on failure
3.  Human checkpoint at: before_start
4.  Reserve budget: min(node constraints, remaining global)
5.  Route the model                        (§11.4)
6.  Run the agentic loop
      • harness-defined prompting and tool protocol
      • enforce max_agent_steps, max_tool_calls, timeouts, permissions
      • pause at before_side_effects checkpoints on the first mutating tool call
7.  Collect declared outputs; validate type and schema   → validation_error / output_missing
8.  Human checkpoint at: after_outputs
9.  Evaluate success                       (§10.3)
10. On failure: on_criteria_failure checkpoint, then the failure ladder  (§14.2)
11. Reach a terminal state; record usage, attempts, evidence
```

Type-specific execution replaces steps 5–9:

- **`decision`** — the agent (or expression evaluator) selects one branch label; `outputs.decision`
  is set; `success`, if declared, is still evaluated.
- **`gate`** — steps 5–7 are replaced by the human interaction described in §7.3.
- **`loop`** — a fresh body scope is created per iteration; the iteration's internal graph is
  scheduled by the same algorithm; `carry` feeds the next iteration; `collect` produces the node's
  outputs from the final iteration.
- **`map`** — one body scope per element, bounded by `max_items` and `max_parallel`; `collect`
  gathers results **in input order**.
- **`subgraph`** — the child document is loaded, validated and run as a nested run with its own run
  record (`parent_run_id` set); `outputs_from` maps its results out.

### 17.8 Termination

The run terminates when no node is in `ready`, `running` or `awaiting_human`, or when a global
constraint or operator action stops it. Final status:

| Status | Condition |
| --- | --- |
| `succeeded` | All required graph outputs bound, graph `success` passes, no unabsorbed `failed` node. |
| `partial` | Some required output unbound, or a node ended `succeed_degraded`, but the run was not stopped by a failure. |
| `failed` | An unabsorbed node failure with `policy.on_node_failure: halt`, or graph `success` failed, or a fatal error. |
| `cancelled` | Operator or global-budget termination. |
| `awaiting_human` | Suspended at a checkpoint with `on_timeout: hold`; resumable. |

### 17.9 Resumption

With `policy.checkpointing` other than `none`, a harness MUST be able to resume a suspended or
crashed run. On resume with `policy.resume: resume_incomplete` (the default), terminal nodes keep
their state and outputs, and scheduling restarts from §17.4. `resume_failed` additionally resets
`failed` nodes to `pending`. `restart` discards prior state.

A harness MUST refuse to resume a run whose `graph_digest` no longer matches the current document
(`RT053`) unless explicitly forced, because node outputs recorded against one decomposition are not
meaningful against another.

---

## 18. Validation

Validation has three layers. A harness MUST implement layers 1 and 2 to claim any conformance level,
and layer 3 to claim level 2 or above.

**Layer 1 — Structural.** JSON Schema validation against
`schema/agentic-graph-1.0.schema.json`. Codes `AG0xx`.

**Layer 2 — Referential.** Cross-reference checks the schema cannot express. Codes `AG1xx`.

**Layer 3 — Semantic.** Expression and dataflow analysis. Codes `AG2xx`/`AG3xx`.

**Advisory.** Quality warnings that never block execution. Codes `AG9xx`.

### 18.1 Rule catalogue

| Code | Sev. | Rule |
| --- | --- | --- |
| `AG001` | error | Document fails JSON Schema validation. |
| `AG002` | error | `ags_version` is not a supported MAJOR.MINOR (§21). |
| `AG003` | error | Unrecognized non-`x-` field and `policy.on_unknown_field` is `error`. |
| `AG004` | error | Unknown enum value in a known field. |
| `AG005` | error | Duplicate mapping key in the YAML source. |
| `AG101` | error | A node declares a type block that does not match its `type`. |
| `AG102` | error | A `gate` node declares `intelligence`. |
| `AG103` | error | A `sequence` edge declares `when`. |
| `AG104` | error | An input declares more than one of `from`, `template`, `value`. |
| `AG111` | error | The effective edge set of a scope contains a cycle. |
| `AG112` | error | An entrypoint has an incoming edge. |
| `AG113` | error | An edge references a node id that does not exist in its scope. |
| `AG114` | error | `depends_on` references a node id that does not exist in its scope. |
| `AG115` | error | `entrypoints` references a node id that does not exist. |
| `AG116` | error | `join: n_of` with `join_count` greater than the node's incoming edge count. |
| `AG117` | error | A node id is `self`, which is a reserved namespace root (Appendix B). |
| `AG121` | error | `decision.evaluator: expression` with a branch missing `when`. |
| `AG122` | error | A `decision` or `gate` node declares an output named `decision`. |
| `AG123` | error | `decision.default_branch` is not one of the declared labels. |
| `AG124` | error | Two branches of one decision share a `label`. |
| `AG131` | error | A subgraph reference is recursive (directly or transitively). |
| `AG132` | error | `loop.use` / `map.use` / `subgraph.use` names a fragment not in `graph.subgraphs`. |
| `AG133` | error | A fragment's `entrypoints` reference nodes outside the fragment. |
| `AG141` | error | `intelligence.tier` and `intelligence.level` disagree. |
| `AG142` | error | `intelligence.escalate_to` is a lower tier than `intelligence.tier`. |
| `AG151` | error | `fallback.alternate_node` names a node whose outputs are not a superset of this node's required outputs. |
| `AG152` | error | A compensation node declares its own `compensation`. |
| `AG153` | error | `fallback.relax_criteria` / `degrade_outputs` names a criterion / output the node does not declare. |
| `AG201` | error | An expression reads `nodes.X.outputs.*` where `X` is not a transitive predecessor in the effective edge set. |
| `AG202` | error | An expression inside a fragment references `nodes.*` outside the fragment. |
| `AG203` | error | An expression references an undeclared `params.*`, `context.*`, `attachments.*` or `env.*` name. |
| `AG204` | error | An expression is syntactically invalid, or calls an unknown function or wrong arity. |
| `AG205` | error | An expression references `secrets.*`. |
| `AG206` | error | An expression references an output name the target node does not declare. |
| `AG211` | error | `${{ }}` interpolation used in expression position, or a bare expression used where a template is expected and the result is ambiguous. |
| `AG301` | error | A required `param` has no supplied value and no `default` (run time). |
| `AG302` | error | A supplied `param` violates its `enum` or `schema` (run time). |
| `AG303` | error | `requires_conformance` exceeds the harness's level. |
| `AG901` | warn | Both a `depends_on` entry and an explicit edge exist for the same `(from, to)` pair. |
| `AG902` | warn | A node with `requirements.workspace: read_write` or mutating permissions declares no `success` block. |
| `AG903` | warn | A node is unreachable from any entrypoint. |
| `AG904` | warn | A node declares an output that no other node, graph output, or criterion reads. |
| `AG905` | warn | A node at `intelligence.tier: frontier` declares no `rationale`. |
| `AG906` | warn | A `success` block consists only of `llm_judge` and/or `human` criteria (no deterministic check). |
| `AG907` | warn | A node declares `constraints.determinism: strict` without a `seed`. |
| `AG908` | warn | Graph declares no `constraints.max_cost_usd` and no node declares `estimate`, so the run's cost cannot be previewed. |
| `AG909` | warn | A `subgraph.ref` to a non-local URI declares no `integrity` digest. |

### 18.2 Runtime diagnostic codes

Runtime problems use `RT` codes and appear in the run record's `diagnostics`.

| Code | Meaning |
| --- | --- |
| `RT011` | Cannot satisfy `intelligence.tier` and `allow_downgrade` is false. |
| `RT012` | A required tool is unavailable. |
| `RT013` | `determinism: strict` cannot be honored. |
| `RT014` | Requested `isolation` cannot be provided. |
| `RT015` | A human checkpoint could not be presented. |
| `RT021` | Loop hit `max_iterations`. |
| `RT022` | Decision agent returned a label outside the declared set; `default_branch` used. |
| `RT025` | `map.over` did not evaluate to an array. |
| `RT026` | `map` collection exceeded `max_items`. |
| `RT031` | An output failed its `type` check. |
| `RT032` | An output failed its `schema` check. |
| `RT033` | A required input or output was missing. |
| `RT041` | A required graph output could not be bound. |
| `RT042` | A node ended `succeed_degraded`. |
| `RT051` | Subgraph `integrity` digest mismatch. |
| `RT052` | Subgraph `expected_id` mismatch. |
| `RT053` | Resume refused: `graph_digest` mismatch. |
| `RT061` | A global constraint was exceeded. |
| `RT062` | An expression evaluation error occurred (with `policy.on_expression_error: false`). |

---

## 19. Conformance levels

A harness advertises an integer level. Each level includes everything below it.

### Level 0 — Reader

Parses JSON and YAML, validates layers 1 and 2, resolves `depends_on` into the effective edge set,
computes topological order and reachability, and renders a plan. Does **not** execute. Editors,
linters, visualizers and CI checks live here.

### Level 1 — Minimal harness

Everything in level 0, plus execution of:

- node types `task` and `gate`;
- edge kind `sequence` (and therefore `depends_on`);
- `join: all`;
- `inputs` / `outputs` with `from`, `value`, `default` and implicit binding;
- criterion kinds `command`, `file_exists`, `artifact_present`, `human`;
- `intelligence` routing per §11.4, including the refusal in rule 2;
- `failure.retry` and `failure.on_exhausted`;
- `human` checkpoints at `before_start` and `after_outputs`;
- sequential scheduling (`max_parallel_nodes` MAY be treated as `1`).

A level 1 harness MUST reject documents that use higher-level features rather than ignoring them,
and MUST report exactly which features it lacks.

### Level 2 — Standard harness

Everything in level 1, plus:

- node type `decision`;
- edge kinds `conditional` and `on_failure`, and node-level `when`;
- `join: any` and `n_of`;
- the full AGX language (§16) and validation layer 3;
- criterion kinds `expression`, `regex`, `json_schema`;
- enforcement of all `constraints` and `graph.constraints`, including real parallel scheduling;
- `failure.fallback` and `failure.escalation`;
- all `human` checkpoint stages including `before_side_effects`;
- `policy` switches.

### Level 3 — Full harness

Everything in level 2, plus:

- node types `loop`, `map`, `subgraph` (including external `ref` with integrity verification);
- criterion kinds `llm_judge` and `external`;
- `failure.compensation`;
- run records (§20), checkpointing and resumption;
- extension negotiation (§23).

### Declaring and negotiating

A graph declares `requires_conformance`. A harness MUST refuse a graph above its level with
`AG303`. A harness SHOULD also publish a feature list (used in the run record's
`harness.supported_features`) so tooling can explain precisely what is missing rather than only
citing a level.

---

## 20. Run records

A **Run Record** is a portable, machine-readable account of one execution, conforming to
[`schema/agentic-graph-run-1.0.schema.json`](schema/agentic-graph-run-1.0.schema.json). Emitting one
is REQUIRED at conformance level 3 when `policy.record_run` is true.

A run record carries the run's status and usage, per-node states with every attempt, what the
router actually chose (`attempt.routed`, including whether it downgraded), every criterion result
with its evidence, every human event, the edges that were taken and the guards that decided them,
and all diagnostics.

It exists to answer three questions after the fact:

1. **What actually happened, and why did it stop?** — states, diagnostics, edge activations.
2. **Was the definition of done really met?** — criterion results with evidence.
3. **Can this be resumed or reproduced?** — `graph_digest`, per-node outputs, routing decisions.

Records MUST NOT include values from inputs or outputs marked `redact: true`, nor any secret value.
`transcript_ref` is an opaque handle; the full agent transcript stays in the harness.

---

## 21. Versioning and compatibility

### 21.1 What versions mean

- `ags_version` is `MAJOR.MINOR` of **this specification**. Patch-level spec releases fix wording
  and never change the data model, so they are not expressible in a document.
- `version` on a document is the **author's** semver for that graph design. Unrelated to
  `ags_version`.

### 21.2 Compatibility rules

**MINOR releases are backward compatible.** A MINOR release may:

- add new optional fields;
- add new enum values, provided they are gated behind a conformance level or an `x-` extension;
- add new advisory validation rules;
- relax a constraint (widen a range, make a required field optional).

A MINOR release MUST NOT: remove or rename a field, make an optional field required, narrow an
enum, change a default, or change the meaning of an existing field.

**MAJOR releases may break anything**, and get a new `$id` and a new schema file. Both versions'
schemas remain published.

### 21.3 Harness obligations

Given a document with `ags_version` `X.Y` and a harness supporting up to `X.Z`:

| Case | Harness behavior |
| --- | --- |
| Different `X` | MUST refuse (`AG002`). |
| `Y ≤ Z` | MUST process. |
| `Y > Z`, `policy.on_unknown_field: error` | MUST refuse (`AG002`). |
| `Y > Z`, `policy.on_unknown_field: warn` | MAY process using the known subset, MUST emit a warning naming every field it ignored, and MUST record `harness.conformance_level` and the ignored fields in the run record. |

### 21.4 Deprecation

A field being removed is marked deprecated in the schema `description` and in this document for at
least one MINOR release before the MAJOR release that removes it. Deprecated fields keep working
until removal. Validators SHOULD emit an advisory when a deprecated field is used.

### 21.5 Extension promotion

An `x-` extension that becomes widely implemented may be promoted to a real field in a MINOR
release. When promoted, the `x-` form MUST continue to be accepted for one MAJOR cycle, and a
document that sets both is an error.

---

## 22. Security considerations

**A graph document is untrusted input.** A harness that accepts graphs from users MUST treat every
string in the document as data, never as instruction to the harness itself. In particular:

- **Prompt injection surface.** `description`, `instructions`, `rubric` and `prompt` are placed in
  front of models. A harness MUST NOT let content from those fields expand the node's permissions,
  tools, or budget. The declared `requirements` and `constraints` are the ceiling; nothing the model
  reads or writes can raise it.
- **Permissions are a request, not a grant.** `requirements.permissions` declares what the node
  *wants*. The harness's own policy decides what it *gets*, and MUST intersect the two. A graph
  asking for `fs:write:/**` gets whatever the harness's policy allows, or the node is `blocked`.
- **Secrets never live in documents.** Only names appear (§5.2). `secrets.*` is unreachable from
  AGX (`AG205`). A harness MUST NOT write secret values into run records, logs or transcripts.
- **Command criteria execute code.** `kind: command` runs a shell command. A harness MUST run it
  under the node's permissions and isolation, MUST apply `timeout_seconds`, and SHOULD require
  explicit operator opt-in before executing command criteria from a graph submitted by a third
  party.
- **External subgraph references fetch code.** `subgraph.ref.uri` pulls in another document. A
  strict harness MUST require `integrity` for non-local URIs, MUST verify it, and SHOULD restrict
  the set of permitted origins.
- **Resource exhaustion.** `max_iterations`, `max_items`, `max_subgraph_depth` and
  `max_node_executions` exist precisely to bound a hostile or buggy graph. A harness MUST enforce
  them and SHOULD impose its own hard caps on top, independent of the document.
- **Fan-out amplification.** A `map` inside a `loop` inside a `subgraph` multiplies. Harnesses
  SHOULD compute the worst-case node execution count during PLAN and refuse or warn before running.
- **Human checkpoints are a safety control.** A harness MUST NOT silently skip a required human
  checkpoint it cannot present (`RT015`). Defaulting `on_human_timeout` to `approve` defeats the
  control and SHOULD be disallowed by policy for anything but `notify`.

---

## 23. Extensibility

Every object in the data model accepts members whose names begin with `x-`. Harnesses MUST preserve
unknown `x-` members when re-serializing a document and MAY ignore them entirely.

Extension names SHOULD be namespaced by vendor: `x-acme-priority`, not `x-priority`. An extension
MUST NOT change the meaning of a normative field; if honoring it would alter execution semantics, it
belongs behind a conformance-level feature, not an extension.

A harness at level 3 SHOULD publish the `x-` extensions it understands in
`harness.supported_features` so authors can tell whether their extensions will be honored.

---

## Appendix A — Defaults index

| Field | Default |
| --- | --- |
| `requires_conformance` | `1` |
| `node.type` | `task` |
| `node.join` | `all` |
| `edge.kind` | `sequence` |
| `input.required`, `output.required`, `param.required` | `true` |
| `input.redact`, `output.redact` | `false` |
| `success.mode` | `all` |
| `success.evaluation_order` | `declared` |
| `criterion.severity` | `required` |
| `criterion.record_evidence` | `true` |
| `criterion.expect_exit_code` | `0` |
| `criterion.threshold` (llm_judge) | `0.8` |
| `criterion.samples` (llm_judge) | `1` |
| `intelligence.allow_downgrade` | `false` |
| `requirements.network` | `none` |
| `requirements.workspace` | `read_only` |
| `constraints.determinism` | `relaxed` |
| `constraints.isolation` | `shared` |
| `retry.max_attempts` | `1` |
| `retry.backoff` | `exponential` |
| `retry.initial_delay_seconds` | `2` |
| `retry.max_delay_seconds` | `60` |
| `retry.jitter` | `true` |
| `retry.retry_on` | `[transient, tool_error, criteria_failed]` |
| `retry.feedback` | `failed_criteria` |
| `retry.escalate_intelligence` | `false` |
| `failure.on_exhausted` | `fail` |
| `failure.timeout_action` | `fail` |
| `human_checkpoint.required` | `true` |
| `gate.on_reject` | `fail` |
| `loop.on_max_iterations` | `fail` |
| `map.max_parallel` | `1` |
| `map.on_item_failure` | `fail_fast` |
| `map.on_over_limit` | `fail` |
| `map.index_as` | `index` |
| `subgraph.inherit_context` | `false` |
| `graph.constraints.max_parallel_nodes` | `1` |
| `graph.constraints.max_subgraph_depth` | `5` |
| `policy.on_expression_error` | `fail` |
| `policy.on_node_failure` | `isolate` |
| `policy.on_unknown_field` | `error` |
| `policy.on_human_timeout` | `hold` |
| `policy.checkpointing` | `per_node` |
| `policy.resume` | `resume_incomplete` |
| `policy.record_run` | `true` |

## Appendix B — Reserved names

The following names are reserved and MUST NOT be used as user-defined output or binding names:

- Output name `decision` on `decision` and `gate` nodes (`AG122`).
- Namespace roots: `graph`, `params`, `context`, `attachments`, `nodes`, `self`, `loop`, `outputs`,
  `env`, `secrets`, `item` (reserved for future default `map.as`).
- Node id `self`.
- Any field name beginning with `x-` at a position where the spec defines a normative field.

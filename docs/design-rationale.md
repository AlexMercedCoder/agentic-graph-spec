# Design rationale

Why AGS is shaped the way it is, and what was considered and rejected. Non-normative;
[SPEC.md](../SPEC.md) is the specification.

---

## The graph is acyclic

**Decision.** The top-level graph and every fragment must be a DAG. Iteration is a `loop` node that
owns a body fragment; fan-out is a `map` node. There are no back-edges.

**Alternative considered.** Allow cycles with a designated loop header and a `loop_back` edge kind,
the way most workflow engines do.

**Why not.** Cycles make four things hard at once: topological ordering, readiness computation when
a node can be re-entered, skip propagation (which node "already resolved" when it may resolve
again), and budget attribution across iterations. They also make termination unprovable by
inspection — you cannot look at a cyclic document and say how many times it might run.

Body-owning loops give the same expressive power. `max_iterations` is required and capped, so worst-
case execution count is computable at load time. The parent graph stays sortable, and a loop is one
vertex in it.

**Cost.** Sharing nodes between the loop body and the main graph requires either duplicating them or
putting them in `subgraphs` and referencing them from both. That is a real ergonomic cost, and it is
the price of static analyzability.

## Control flow and data flow are separate

**Decision.** Edges carry control flow only. Data flow lives in `inputs.*.from`.

**Alternative considered.** Typed data edges, where an edge declares `outputs → inputs` mappings and
implies the dependency.

**Why not.** Data edges conflate two questions that have different answers often enough to matter:
"what must finish before this starts" and "what does this read". A node may depend on another purely
for ordering (a migration before a query) with no data passing, or read from a node several hops
upstream. With data edges you either invent a second edge kind for pure ordering, or invent
pass-through data no one uses.

Separating them means each mechanism is simple. The safety property that data edges buy — you cannot
read something that has not run — is recovered as a validation rule (`AG201`, the predecessor rule),
which is strictly more flexible because it works across transitive paths.

`edge.carries` exists as documentation-only sugar for rendering, explicitly non-authoritative.

## Nodes are a map, not an array

**Decision.** `nodes` is an object keyed by node id.

**Why.** Uniqueness of node ids is a data-model property rather than a validation rule, and
references read naturally (`nodes.build_docs.outputs.site`). JSON Schema cannot express "these array
elements must have unique `id` fields", so the array form would have required a rule the schema
could not enforce — exactly the kind of gap that lets non-conformant documents through a
schema-only validator.

**Cost.** Declaration order is not guaranteed to be preserved by every parser, which is why
scheduling tie-breaks fall back to topological order first and declaration order second, and why
determinism is specified rather than assumed.

## `depends_on` is sugar over `edges`

**Decision.** Both exist. `depends_on` desugars to `sequence` edges; the effective edge set is the
deduplicated union.

**Why both.** Ninety percent of edges in a real graph are plain dependencies, and
`depends_on: [design]` is dramatically more readable than a separate edges array entry — especially
in YAML, where the dependency then sits next to the node it belongs to. But conditional and failure
edges need their own object with `when`, `kind` and `label`, and hanging those off the target node
reads backwards.

The risk is two ways to say one thing. That is contained by making the desugaring normative and
mechanical, deduplicating exact matches silently, and emitting advisory `AG901` when the same pair
is declared both ways.

## Capability is a tier, not a model

**Decision.** `intelligence.tier` is an ordered four-value scale. No model, provider or parameter
count appears anywhere in the normative model.

**Alternatives considered.** (a) Name the model. (b) Declare required capabilities as a feature list
(`needs_tool_use`, `needs_200k_context`). (c) A continuous 0–1 difficulty score.

**Why not (a).** It expires. A graph written today naming a specific model is wrong in six months
and unrunnable on a harness with a different provider. It is also the single thing most likely to
make a graph non-portable.

**Why not (b).** Feature lists describe the *model*, not the *task*, and they do not order. A harness
cannot answer "is this good enough" from an unordered set. Concrete capabilities survive as `hints`
and as `min_context_tokens`, both of which are genuinely feature-shaped.

**Why not (c).** A continuous score invites false precision and inter-author inconsistency: nobody
agrees whether a task is 0.6 or 0.7, and nothing in a routing profile can use the difference. Four
tiers with worked calibration examples produce more consistent labels across authors.

**Why four.** Three collapses "ordinary work" and "needs real reasoning", which is the distinction
that actually drives routing. Five or more produces adjacent tiers no one can distinguish. Four maps
cleanly onto the model classes harnesses actually have: a small fast one, a mid one, a large one,
and the best one available.

The `level` integer mirror exists so routing code can compare arithmetically without a lookup table,
and validation rule `AG141` keeps the two spellings honest.

## Success is evaluated, not asserted

**Decision.** A node succeeds when the *harness* evaluates its `success` criteria and they pass, not
when the agent stops.

**Why.** "The agent said it was done" is the failure mode that makes multi-step agent runs
untrustworthy: one node claims success on incomplete work, and every downstream node builds on it.
Making completion a harness-side check is the single highest-value constraint in the format.

Two consequences were designed in deliberately:

- **`description` is required on every criterion, including machine-checkable ones.** The
  human-readable statement is what a reviewer reads and what gets injected into retry feedback. A
  bare `run: pytest -q` tells a retrying agent nothing about what it was supposed to achieve.
- **Retry feedback defaults to `failed_criteria`.** A retry that re-sends the identical prompt is a
  coin flip. A retry that says "you claimed done, but this command exited 1 with this output" is a
  different task.

`llm_judge` exists because some work genuinely is not mechanically checkable, and pretending
otherwise pushes authors into writing fake `command` criteria. It is fenced: `samples` with a median
for stability, a required `rubric`, and advisory `AG906` when a node's required criteria are *only*
judged or human.

## Everything is bounded by construction

**Decision.** `loop.max_iterations` and `map.max_items` are required, not optional. Both are capped
in the schema. Graphs may declare `max_node_executions`.

**Why.** The realistic failure mode of an agentic graph is not a wrong answer, it is a loop that
burns a budget overnight. Making the bound required means there is no way to write an unbounded
document — a validator can compute worst-case execution count from any conformant graph, and a
harness can refuse before running.

**Cost.** Authors must pick a number for cases where they genuinely do not know. That is the point:
picking a wrong ceiling produces a diagnosable `RT021`, while having no ceiling produces a bill.

## Fragments are sealed

**Decision.** A node inside a loop, map or subgraph body cannot reference `nodes.*` outside the
fragment. Everything arrives through `params`.

**Why.** A fragment that reaches into its parent is not reusable, cannot be moved into `subgraphs`,
and cannot be extracted to a file. Sealing them makes the `use` / `inline` / `ref` forms
interchangeable, which is what makes composition work at all.

Parent `defaults` also do not leak into fragments, for the same reason.

## Secrets are unreachable from expressions

**Decision.** Only secret *names* appear in a document. `secrets.*` in any AGX expression is a
validation error (`AG205`). Values reach a node only via `requirements.secrets`, injected by the
harness.

**Why.** Graph documents get committed, diffed, pasted into issues, and generated by models. Any
path from a secret into an expression is a path into a log, a run record, a retry feedback block or
a model's context. Making it a *load-time error* rather than a runtime redaction means the mistake
cannot be made.

## Four conformance levels

**Decision.** Levels 0–3, with a graph declaring `requires_conformance` and a harness required to
*reject* rather than degrade.

**Why not one level.** A specification that demands loops, maps, subgraphs, judged criteria,
compensation and resumable run records before anything works is a specification nobody implements.
Level 1 is a weekend of work on top of an existing agent loop and is genuinely useful.

**Why rejection rather than best-effort.** Silently ignoring `loop.max_iterations` or skipping a
human approval a harness cannot present converts a safety control into a no-op. `RT015` — fail
rather than skip an unpresentable checkpoint — is the same principle applied at run time.

## What was left out

| Considered | Why not in 1.0 |
| --- | --- |
| **A transport/API for submitting graphs** | Out of scope. The document format is the interoperability surface; every harness already has its own invocation path. |
| **Cost model / pricing in the document** | Prices change weekly and vary by provider. `estimate.cost_usd` is a non-binding planning hint; real accounting belongs in the run record. |
| **Agent personas / role definitions on nodes** | Harnesses model this incompatibly (system prompts, named agents, skill bundles). `requirements.skills` is the portable hook; a persona is an `x-` extension. |
| **Streaming / event-driven triggers** | AGS describes a bounded project decomposition, not a long-lived reactive system. A triggered run is the harness's concern. |
| **Full type system for inputs and outputs** | `type` is a marshalling hint with `schema` as the escape hatch for anything structured. A real type system would be most of the spec's complexity for a fraction of its value. |
| **Cross-node shared mutable state** | Deliberately absent. State moves along declared edges through `outputs` and `inputs`, or through the workspace. A shared scratchpad would make dataflow unanalyzable. |
| **Priorities / deadlines per node** | `constraints.deadline` and `concurrency_group` cover the cases that affect correctness. Scheduling policy beyond that is a harness quality-of-implementation matter. |
| **A canonical visual notation** | Worth doing; needs implementation experience first. `edge.label` and `node.labels` exist to support renderers in the meantime. |

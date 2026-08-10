# Glossary

Terms of art used by the Agentic Graph Specification. Definitions here are informative; where a term
has normative force, [SPEC.md](SPEC.md) governs.

---

**Advisory criterion** — A `success` criterion with `severity: advisory`. Evaluated and recorded,
but never gates progression. See [SPEC.md §10.1](SPEC.md#101-the-success-block).

**Agentic Graph** — A directed acyclic graph whose nodes are agentic loops and whose edges are
control-flow dependencies, serialized as a single JSON or YAML document.

**Agentic loop** — One bounded run of an agent: given a brief, inputs, tools and a budget, it
iterates — reasoning, calling tools, producing artifacts — until it stops. A `task` node *is* an
agentic loop. How the loop works internally is entirely the harness's business.

**AGS** — Agentic Graph Specification. This spec. `AGS 1.0` is the version documents target through
`ags_version`.

**AGX** — The small, pure, side-effect-free expression language used by conditions, bindings and
`expression` criteria. See [docs/expressions.md](docs/expressions.md).

**Attachment** — Shared reference material (a file, a URL, or inline text) declared once at graph
level and pulled into node context by name.

**Author** — The human or agent that produced a graph document. Recorded in `authors`; a generating
harness should record itself with `role: generator`.

**Body** — The graph fragment a `loop` or `map` node iterates over, either inline (`body`) or by
name (`use`).

**Branch label** — One of the enumerated outcomes a `decision` node may select. The selected label
is exposed as `nodes.<id>.outputs.decision`.

**Canonical form** — The JSON serialization with sorted member names and no insignificant
whitespace, used for computing digests. See [SPEC.md §3.3](SPEC.md#33-canonical-form-and-digests).

**Carry** — The `loop.carry` map that feeds an iteration's output into the next iteration's
parameter. The only channel for state between loop iterations.

**Checkpoint** — Either (a) a *human checkpoint*: a `human[]` entry attaching a person to a moment in
a node's lifecycle; or (b) *checkpointing*: persisting run state so a run can be resumed.

**Collect** — The `loop.collect` / `map.collect` map that turns values from a fragment's final scope
into outputs of the containing node.

**Compensation** — A node that undoes another node's side effects when a run halts after that node
succeeded. The saga-pattern escape hatch. Conformance level 3.

**Conformance level** — 0 (Reader), 1 (Minimal), 2 (Standard) or 3 (Full). A harness advertises one;
a graph demands a minimum with `requires_conformance`. See
[SPEC.md §19](SPEC.md#19-conformance-levels).

**Criterion** — One acceptance check inside a `success` block. Has a `kind`, a required
human-readable `description`, and kind-specific check fields.

**Decision node** — A node whose job is to select exactly one branch label from an enumerated set,
either by a model (`evaluator: agent`) or by evaluating guards (`evaluator: expression`).

**Definition of done** — Informally, a node's `success` block; specifically, its `success.summary`.

**Determinism** — `constraints.determinism`: `strict` (byte-identical outputs required),
`reproducible` (equivalent outputs expected), or `relaxed` (no guarantee).

**Diagnostic** — A `{code, severity, message, pointer}` record. `AGnnn` codes are validation
findings; `RTnnn` codes are runtime findings recorded in the run record.

**Edge activation** — The resolution of an edge to `active` or `inactive` once its source node
reaches a terminal state. Governed by the table in [SPEC.md §17.3](SPEC.md#173-edge-activation).

**Effective edge set** — The deduplicated union of explicit `edges` and the `sequence` edges
desugared from every node's `depends_on`. The only edge set anything downstream should use.

**Entrypoint** — A node listed in `entrypoints`, made `ready` at run start. Must have no incoming
edges.

**Escalation** — Handing a failing node to a human, another node, the harness's own planner, or an
external system. The rung of the failure ladder after fallbacks.

**Evidence** — What a criterion recorded when it was evaluated: command output, the matched text, a
judge's reasoning, a reviewer's note. Feeds retry feedback and the run record.

**Failure class** — The classification of an unsuccessful attempt: `transient`, `model_error`,
`tool_error`, `timeout`, `budget_exceeded`, `criteria_failed`, `output_missing`,
`validation_error`, `permission_denied`. Drives `retry.retry_on`.

**Failure ladder** — The ordered sequence a non-succeeding node walks:
retry → fallback → escalation → `on_exhausted`.

**Fallback** — An alternate strategy tried after retries are exhausted: run a different node, accept
degraded outputs, relax named criteria, hand to a human, or skip.

**Fragment** — A self-contained set of nodes and edges with its own entrypoints and parameters, used
as a loop body, a map body, or an inline subgraph. Fragments are *sealed*: they cannot reference
nodes outside themselves.

**Gate** — A node whose entire purpose is a human decision. Never calls a model; `intelligence` is
forbidden on it.

**Graph fragment** — See *Fragment*.

**Harness** — The software that loads, validates, schedules and executes an Agentic Graph. The
implementer audience for this spec.

**Hint** — An entry in `intelligence.hints`. Unordered and advisory; used to choose among models
that already satisfy the tier, never to override it.

**HITL** — Human in the loop. Realized as `gate` nodes and `human[]` checkpoints.

**Implicit binding** — Resolving an input by name from the enclosing scope (`params.<name>`, then
`context.<name>`) when it declares no `from`, `template` or `value`.

**Intelligence tier** — `minimal`, `standard`, `advanced` or `frontier`: a normalized, ordered
statement of how capable a model must be for a node. See
[SPEC.md §11](SPEC.md#11-intelligence-tiers-and-model-routing).

**Join** — How a node's multiple incoming edges combine into readiness: `all` (default), `any`, or
`n_of` with `join_count`.

**Judge** — An `llm_judge` criterion: a model scores material against a rubric, and the score is
compared to a threshold.

**Map node** — A node that runs a body fragment once per element of a collection, bounded by
`max_items` and `max_parallel`.

**Node** — One vertex: a unit of work with a brief, inputs, outputs, acceptance criteria, a
capability demand, requirements, constraints and failure handling.

**Permission** — A `scope:action[:target]` string in `requirements.permissions`. A *declared
ceiling*, intersected with the harness's own policy — never a grant.

**Plan** — The output of the PLAN phase: topological order, reachability, worst-case execution
count, projected cost, tier histogram. Renderable without executing anything.

**Predecessor rule** — Validation rule `AG201`: an expression may read `nodes.X.outputs.*` only when
`X` is a transitive predecessor of the referencing node.

**Requirements** — The tools, permissions, MCP servers, skills, environment variables, secrets,
network access and workspace mode a node needs before it can start.

**Routing profile** — A harness's implementation-defined mapping from intelligence tier to model
class. The main reason the same graph behaves differently in two places.

**Run** — One execution of one graph document.

**Run record** — The portable, machine-readable account of one run, conforming to
`agentic-graph-run-1.0.schema.json`.

**Scope** — The set of names visible to an expression at a point in the graph. Each fragment
instance (loop iteration, map item, subgraph invocation) creates its own *scope instance*.

**Skip propagation** — The consequence of the activation table: a `skipped` or `cancelled` node
makes all its outgoing edges inactive, so its dependents' joins become unsatisfiable and they too
become `skipped`.

**Subgraph node** — A node that runs another graph as a single unit of work: a named local fragment
(`use`), an inline fragment (`inline`), or another document (`ref`).

**Success block** — A node's or graph's acceptance criteria plus how they combine.

**Task node** — The default node type. One agentic loop.

**Template position** — A text field where `${{ ... }}` interpolation is allowed, as opposed to
*expression position*, where the whole string is an expression.

**Terminal state** — `succeeded`, `failed`, `skipped`, `cancelled` or `blocked`. A node in a terminal
state resolves its outgoing edges and never runs again in that scope instance.

**Tier** — See *Intelligence tier*.

**Worst-case execution count** — Total node executions a graph could produce, multiplying retries,
loop iterations and map widths through every nesting level. Computed during PLAN, bounded by
`constraints.max_node_executions`.

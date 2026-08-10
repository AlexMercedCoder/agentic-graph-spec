# Adding AGS support to an agent harness

A practical guide for someone who already has a working agent loop and wants it to accept, execute
and produce Agentic Graphs. [SPEC.md](../SPEC.md) is normative; this document is the build order.

**Assumed starting point:** you have an agent that can take a task description, call tools, and stop
when it thinks it is finished. That agent loop becomes the *inside* of a node. Everything below is
the *outside*.

---

## 0. What you are actually building

Five components, in dependency order:

```
   Loader ──► Validator ──► Planner ──► Scheduler ──► Node executor
                                            │              │
                                            │              ├─ Model router
                                            │              ├─ Criteria evaluator
                                            │              └─ HITL adapter
                                            └────────────► Run recorder
```

The single most useful reframing: **your existing agent loop is the node executor's inner loop, and
nothing else.** Everything AGS adds sits around it. If you find yourself changing the agent loop
itself, you have probably pushed graph concerns too far down.

## 1. Loader

Parse JSON and YAML into one internal representation.

```python
def load(path_or_text) -> dict:
    if looks_like_yaml:
        doc = yaml.load(text, Loader=NoDuplicateKeyLoader)  # duplicate key -> AG005
    else:
        doc = json.loads(text)
    return doc
```

Requirements that bite later if you skip them:

- **Reject duplicate YAML keys.** The default `yaml.safe_load` silently keeps the last one; a
  duplicated node id would quietly discard a node. Use a loader that raises (see
  `_NoDuplicateLoader` in [`tools/validate_agraph.py`](../tools/validate_agraph.py)).
- **Reject non-JSON YAML constructs**: custom tags, non-string mapping keys.
- **Preserve unknown `x-` keys.** If you round-trip a document, extensions must survive.
- **Compute and keep the canonical digest** ([SPEC.md §3.3](../SPEC.md#33-canonical-form-and-digests)).
  You need it for resume safety and run records, and it costs one function.

## 2. Validator

Do not skip this and "fail at run time instead". A graph is a plan a human is going to approve;
they need to know it is coherent before they approve it, not after node 6 dies.

Three layers, all statically decidable ([SPEC.md §18](../SPEC.md#18-validation)):

| Layer | What | Effort |
| --- | --- | --- |
| 1. Structural | JSON Schema against `schema/agentic-graph-1.0.schema.json` | An afternoon. Use an off-the-shelf validator. |
| 2. Referential | Cycles, dangling ids, entrypoints, joins, decision branches, fragment refs | A day. Plain graph algorithms. |
| 3. Semantic | Expression parsing, scope checks, the predecessor rule | Two days. You need the AGX parser anyway. |

Port [`tools/validate_agraph.py`](../tools/validate_agraph.py) if the license suits you; it is
~900 lines and implements all three plus the advisory rules.

**Return structured findings, not strings.** Every finding should carry `{code, severity, message,
pointer}` with a JSON Pointer into the document. Editors and planning agents both consume this: when
your harness *generates* a graph (§9), the generator loop feeds on exactly these findings.

## 3. Planner

Between validation and execution, produce a plan object that can be rendered without executing
anything. This is conformance level 0, and it is worth shipping on its own.

```python
@dataclass
class Plan:
    scopes: dict[str, ScopePlan]       # root + every fragment
    topological_order: list[str]
    reachable: set[str]
    worst_case_executions: int         # nodes x retries x iterations x map width
    estimated_cost_usd: float | None   # from node.estimate
    tier_histogram: dict[str, int]     # how much frontier work is in here
    unsupported_features: list[str]    # what your level cannot run
```

Two computations pay for themselves immediately:

- **Worst-case execution count.** Multiply through `retry.max_attempts`, `loop.max_iterations` and
  `map.max_items` at every nesting level. A `map` inside a `loop` inside a `subgraph` multiplies,
  and a user pasting a graph from elsewhere has no idea. Compare against
  `constraints.max_node_executions` and refuse or warn *before* running.
- **Tier histogram.** "This graph has three frontier-tier nodes" is the single most useful line you
  can show a human before they approve a plan.

Build the effective edge set here, once ([SPEC.md §8.3](../SPEC.md#83-the-effective-edge-set)):

```python
edges = dedupe(
    explicit_edges
    + [Edge(dep, node_id, "sequence", None)
       for node_id, node in nodes.items()
       for dep in node.get("depends_on", [])]
)
```

Every later stage works on this, never on `depends_on` and `edges` separately.

## 4. Scheduler

The whole scheduler is [SPEC.md §17.4](../SPEC.md#174-the-scheduling-loop):

```python
while any(n.state in {READY, RUNNING, AWAITING_HUMAN} for n in nodes):
    for node in newly_terminal:
        resolve_outgoing_edges(node)          # §17.3 activation table
    recompute_readiness()                     # §17.5 join predicates
    mark_unsatisfiable_as_skipped()           # §17.6
    while capacity_available() and (node := pick_ready()):
        launch(node)
```

Get these four things right and the rest follows.

**Edge activation** is a table, not a special case per node type:

| source terminal state | `sequence` | `conditional` | `on_failure` |
| --- | --- | --- | --- |
| `succeeded` | active | active if `when` | inactive |
| `failed` / `blocked` | inactive | inactive | active if `when` absent or true |
| `skipped` / `cancelled` | inactive | inactive | inactive |

Skip propagation is not separate machinery — it falls out of the bottom row.

**Joins.** `all` waits for every incoming edge to resolve and requires all active. `any` fires on the
*first* active edge and does not wait for the rest. `n_of` fires at `join_count` active. A node runs
at most once per scope instance regardless of edges that resolve later.

**Deterministic tie-breaking is normative.** When two nodes are ready and both fit, pick by
topological order, then by declaration order in the document. Without this, the same graph run twice
sequentially on your harness produces different orders, and users will report it as a bug.

**Concurrency.** Respect `constraints.max_parallel_nodes` and never co-schedule two nodes sharing a
`constraints.concurrency_group`. If you support `isolation: worktree`, nodes in different worktrees
can safely ignore group constraints on the file system — but only if you also merge worktrees
somewhere, which is a design decision worth making explicitly rather than discovering.

**Fragments.** A loop iteration, a map item and a subgraph invocation each create a *scope instance*
with its own node states. The cleanest implementation runs the same scheduler recursively over the
fragment and treats the containing node as `running` until the fragment terminates. Do not try to
inline fragment nodes into the parent scheduler; scoping rules will bite you.

## 5. Node executor

[SPEC.md §17.7](../SPEC.md#177-executing-one-node) is the sequence. In code:

```python
def execute(node, scope, run):
    inputs = resolve_inputs(node, scope)                  # RT033 on failure
    require_capabilities(node)                            # -> BLOCKED, RT011/RT012/RT014
    hitl(node, "before_start")
    budget = min_budget(node.constraints, run.remaining)

    for attempt in range(1, max_attempts(node) + 1):
        routing = route_model(node.intelligence, attempt)  # §11.4
        result  = agent_loop(                              # <- your existing agent
            brief=build_prompt(node, inputs, scope),
            tools=resolve_tools(node.requirements),
            permissions=intersect(node.requirements.permissions, harness_policy),
            budget=budget,
            model=routing.model,
        )
        outputs = collect_outputs(node, result)            # RT031/RT032/RT033
        hitl(node, "after_outputs")
        verdict = evaluate_success(node.success, node, outputs, scope)
        if verdict.passed:
            return succeeded(outputs)
        hitl(node, "on_criteria_failure")
        if not should_retry(node, classify(verdict), attempt):
            break
        inputs = inputs                                    # unchanged, by spec
        feedback = build_feedback(node.failure.retry.feedback, verdict)

    return failure_ladder(node, ...)                       # §14.2
```

Five things people get wrong:

1. **Resolve inputs once.** [SPEC.md §9.2](../SPEC.md#92-inputs): retries reuse the resolved values
   verbatim. Re-resolving makes retries non-reproducible and can change a node's meaning mid-flight.
2. **Retry feedback is the point of retrying.** With the default `feedback: failed_criteria`, the
   next attempt must receive each failed criterion's `description` *and its recorded evidence*. A
   retry that re-sends the identical prompt is a coin flip; a retry that says "you claimed done but
   `pytest tests/test_pagination.py` exited 1 with this output" is a different task.
3. **`before_side_effects` needs a mutation classifier.** You must be able to pause at the node's
   first externally-visible mutation. Classify tool calls by the permission scope they consume:
   `fs:write`, `git:commit`, `git:push`, `net:post`, `shell:exec` of anything not on a read-only
   allowlist. If you cannot do this, you cannot claim conformance level 2, and you must fail nodes
   that request it (`RT015`) rather than skipping the checkpoint.
4. **Outputs are a contract, not a suggestion.** Decide *one* mechanism for how an agent reports
   declared outputs — a final structured message, a dedicated `emit_output` tool, or files at
   `path_hint` — and tell the agent about it in the prompt you build. Then validate against `type`
   and `schema`.
5. **Permissions intersect, never union.** `requirements.permissions` is a ceiling the graph
   requests. Your policy is the ceiling you enforce. The effective set is the intersection; if a
   non-optional requirement falls outside your policy, the node is `blocked`, not degraded.

### Building the node prompt

You already have prompt construction. The node gives you a well-defined set of slots:

| Slot | From |
| --- | --- |
| Task brief | `description`, then `instructions` with `${{ }}` interpolated |
| Why this matters | `rationale` (optional, and arguably better withheld from the executing agent) |
| Inputs | resolved `inputs`, each with its `description` |
| Definition of done | `success.summary` plus each criterion's `description` |
| Deliverables | `outputs`, with names, types, `description` and `path_hint` |
| Shared background | `context`, `attachments` the node references |
| Bounds | `constraints` worth surfacing (step and tool-call ceilings) |
| Retry feedback | on attempt ≥ 2 only |

**Do surface the criteria to the agent.** They are the contract; hiding them and then failing the
node on them wastes attempts. **Do not** let the agent see the criteria as something to satisfy
cosmetically — `command` criteria run independently of anything the agent says.

## 6. Model router

This is the part with no equivalent in most existing harnesses, and it is small.

Define a **routing profile**: a mapping from tier to a model class you have.

```toml
[routing]
minimal  = { provider = "local",     model = "small-fast" }
standard = { provider = "vendor-a",  model = "mid" }
advanced = { provider = "vendor-a",  model = "large" }
frontier = { provider = "vendor-b",  model = "flagship" }
```

Then implement [SPEC.md §11.4](../SPEC.md#114-routing-rules-normative) exactly:

```python
def route(intel, attempt, profile):
    tier = intel.tier
    if attempt > 1 and intel.retry_escalates:
        tier = intel.escalate_to or next_tier_up(tier)
    candidate = profile.get(tier) or profile.best_available()
    if rank(candidate.tier) < rank(tier):
        if not intel.allow_downgrade:
            raise Blocked("RT011", f"cannot satisfy tier {tier}")
        candidate.downgraded = True
    if intel.min_context_tokens and candidate.context < intel.min_context_tokens:
        raise Blocked("RT011", "context window below min_context_tokens")
    return candidate
```

Three rules with teeth:

- **Never route below the requested tier** unless `allow_downgrade` is true. Failing fast and cheap
  beats producing a bad architecture decision from a small model.
- **`min_context_tokens` is a hard floor,** independent of tier.
- **Record what you actually chose** in `attempt.routed`, including `downgraded` and why. This is
  the field that explains why the same graph produced different quality on two harnesses.

`hints` are advisory. Use them to pick *among* models that already satisfy the tier — route
`long_context` to your bigger-window model, `low_latency` to your faster one — never to override the
tier.

If you only have one model, that is fine: publish a routing profile that maps every tier to it, and
be honest in `harness.supported_features`. Users can then read a run record and know the
`frontier` node did not actually get frontier capability.

## 7. Criteria evaluator

One dispatch table. Each evaluator returns `{passed, score?, evidence, error?}`.

| Kind | Implementation notes |
| --- | --- |
| `command` | Run under the node's permissions and isolation. **Always** apply `timeout_seconds`. Capture stdout/stderr as evidence, truncated with `evidence_truncated: true`. |
| `file_exists` | Glob against the workspace; check `min_bytes`. Evidence is the matched path and size. |
| `artifact_present` | Named output present and non-empty. |
| `json_schema` | Validate the named output. Evidence is the first schema error. |
| `regex` | `target` expression or the named output; honor `flags` and `negate`. Evidence is the match or its absence. |
| `expression` | Evaluate AGX; a non-boolean result is an evaluation error, not a failure. |
| `llm_judge` | Route by `judge_intelligence`; take `samples` independent judgements and use the **median**. Evidence is the judge's reasoning. |
| `human` | Blocking; route to the HITL adapter with `roles`. Evidence is the reviewer's note. |
| `external` | Look up `check` in your registry. Unknown name → fail the node, do not skip the criterion. |

Implementation guidance:

- **Evaluate advisory criteria too.** They do not gate, but they are the cheapest quality signal you
  will ever collect, and they belong in the run record.
- **`evaluation_order: cheapest_first` may reorder but must not change the result.** Only
  short-circuit when the outcome is already determined: with `mode: all`, the first required failure
  decides it; with `mode: any`, the first required pass does.
- **Judges are not free and not neutral.** Do not use the same live model instance that produced the
  output as its own judge within one attempt without recording that in the run record. Prefer a
  separate call, and prefer `samples: 3` for anything gating an expensive branch.
- **Evidence is the product.** A criterion that fails without evidence makes retry feedback useless
  and makes the run record unauditable.

## 8. HITL adapter

The interface is small:

```python
class HumanAdapter(Protocol):
    def request(self, req: HumanRequest) -> HumanResponse | Pending: ...
    def poll(self, request_id: str) -> HumanResponse | Pending: ...
```

`HumanRequest` carries the stage (`before_start`, `before_side_effects`, `after_outputs`,
`on_criteria_failure`, `on_failure`, `on_escalation`), the mode (`approve`, `review`, `input`,
`notify`), the rendered prompt, the material from `present`, the `roles`, and the timeout.

Three things to get right:

- **`hold` must actually suspend.** With `policy.checkpointing` on, a node in `awaiting_human` should
  survive process exit and resume later. Long approvals are the normal case, not the edge case.
- **Never silently skip a required checkpoint.** If your harness has no channel to a human, fail the
  node with `RT015`. A skipped approval is a safety control that silently stopped existing.
- **`on_timeout: approve` is dangerous.** Support it, but consider a harness policy that forbids it
  for anything except `notify`.

Implementations range from a CLI prompt to a queue with a web UI to a chat message with buttons. The
graph does not care; keep the adapter behind the interface.

## 9. Generating graphs (the other direction)

Accepting graphs is half the value. The other half is your harness turning "ship v2 of the API" into
a conformant graph the user can review before spending anything.

The pattern that works is **generate → validate → repair → estimate → approve**:

```
1. DECOMPOSE  frontier-tier call: goal + repo context -> draft graph (JSON mode against the schema)
2. VALIDATE   run your own validator; collect findings with JSON Pointers
3. REPAIR     feed findings back; loop until clean or N attempts exhausted
4. ENRICH     fill estimates, tighten tiers, add criteria where AG902/AG906 fired
5. PREVIEW    render the plan: nodes, tiers, projected cost, worst-case executions
6. APPROVE    human edits and approves the graph, not the output
7. EXECUTE    normal path
```

Notes from the shape of the format:

- **Generate against the JSON Schema, not free-form.** Every serious model API supports constrained
  or schema-guided output. It converts most structural errors into non-events.
- **Your validator's advisory rules are the quality bar.** `AG902` (side-effecting node with no
  criteria), `AG906` (only judged criteria, no deterministic check), `AG904` (output nobody reads)
  and `AG905` (frontier tier with no rationale) are exactly the mistakes a generating model makes.
  Run with `--strict` on generated graphs and make the generator fix them.
- **Decompose in two passes.** First produce nodes, dependencies and objectives only. Then, per
  node, generate `success`, `intelligence`, `requirements` and `constraints`. One-shot generation of
  a fully-specified 12-node graph reliably produces vague criteria; the second pass, given one node
  at a time, produces criteria you can actually run.
- **Make the generator justify tiers.** Requiring `rationale` for `advanced` and `frontier` measurably
  reduces tier inflation, and gives the reviewing human something to push back on.
- **Round-trip your own internal plans.** If your harness already has a plan or task record, an
  exporter to AGS is usually a day of work and immediately gives users a reviewable, diffable
  artifact plus portability.

## 10. Run records

Emit [`schema/agentic-graph-run-1.0.schema.json`](../schema/agentic-graph-run-1.0.schema.json).
Required at level 3; worth doing at level 1.

Record per attempt: status, timings, `routed` (requested tier, effective tier, provider, model,
`downgraded`, reason), usage, criteria results with evidence, and an opaque `transcript_ref`. Record
per run: `graph_digest`, edge activations with their `when` results, diagnostics, and final status.

Never write values from `redact: true` inputs/outputs, and never write a secret value.

The digest is what makes resume safe: refuse to resume a run against a document whose digest changed
(`RT053`), because node outputs recorded against one decomposition are not meaningful against
another.

## 11. Suggested build order

| Milestone | Ship | Effort |
| --- | --- | --- |
| **M1** | Loader + validator + planner. Level 0. A `validate` and a `plan --render` command. | 3–5 days |
| **M2** | Sequential executor: `task` + `gate`, `depends_on`, `join: all`, `command`/`file_exists`/`artifact_present` criteria, retries, tier routing. Level 1. | 1–2 weeks |
| **M3** | AGX evaluator, `decision` nodes, conditional and `on_failure` edges, all joins, budgets, parallelism, fallback/escalation, all HITL stages. Level 2. | 2–3 weeks |
| **M4** | `loop`, `map`, `subgraph`, `llm_judge`, compensation, run records, resume. Level 3. | 2–4 weeks |
| **M5** | Graph generation (§9) and a plan-review UI. | 2–3 weeks |

M2 is the milestone that makes the format real for users. M5 is the one that makes it get used.

## 12. Testing your implementation

- Run `tools/run_checks.sh` from this repository against your own validator.
- Every fixture in [`conformance/invalid/`](../conformance/invalid/) has an `# EXPECT:` header naming
  the diagnostic it must produce.
- Execute [`examples/minimal.agraph.yaml`](../examples/minimal.agraph.yaml) end to end. That is
  level 1.
- Assert scheduling determinism: run the canonical example twice with `max_parallel_nodes: 1` and
  compare the node order.
- Assert budget enforcement: set `constraints.max_node_executions: 3` on a larger graph and confirm
  the run stops with `partial`, not with an exception.
- Assert the routing refusal: request `tier: frontier` with `allow_downgrade: false` on a harness
  configured with only a small model, and confirm you get `RT011` before any tokens are spent.
- Assert the fragment seal: a loop-body node referencing a parent node must fail validation with
  `AG202`.

## 13. Common mistakes

| Mistake | Why it hurts |
| --- | --- |
| Treating `depends_on` and `edges` as two systems | They are one effective edge set. Compute it once, in the planner. |
| Implementing loops as back-edges | AGS graphs are acyclic on purpose. A back-edge breaks topological order, skip propagation and termination analysis all at once. |
| Re-resolving inputs on retry | Makes retries non-reproducible and can silently change what the node is being asked to do. |
| Letting an agent self-report success | The whole point of `success.criteria` is that the harness checks. |
| Ignoring unsupported features | A level 1 harness must *reject* a level 3 graph, not run a partial version of it and report success. |
| Unioning permissions on `defaults` merge | Arrays are replaced, never merged. Silently widening permissions is a security bug. |
| Letting node text change node permissions | `description`, `instructions` and `rubric` are untrusted content placed in front of a model. `requirements` and `constraints` are the ceiling. |
| No worst-case execution estimate | A `map` inside a `loop` inside a `subgraph` multiplies, and nobody notices until the bill. |

# Packaging AGS support as an agent skill

Most agent harnesses now support some form of *skill*, *playbook*, *plugin* or *recipe*: a bundle of
instructions and helper scripts that an agent loads on demand when a task matches. This document
describes how to package Agentic Graph support that way, so an agent can **author**, **validate**,
**review** and **run** graphs without the harness itself having to grow native support first.

A skill is the fastest route to AGS support. A harness integration
([harness-integration.md](harness-integration.md)) is the durable one. They compose: a skill that
shells out to a native `graph run` command is the natural end state.

---

## 1. What the skill has to do

Three capabilities, in the order users need them:

| Capability | Trigger | Output |
| --- | --- | --- |
| **Author** | "break this project into tasks", "plan this out as a graph" | A conformant `.agraph.yaml` the user can read and edit |
| **Validate** | any time a graph is written or edited | Structured findings, then a repair loop |
| **Execute** | "run the graph", "start on step 3" | Node-by-node execution with criteria checked |

A skill that only does the first two is already worth shipping. Authoring plus validation turns an
agent into a planner whose plans are reviewable artifacts; execution can follow.

## 2. Layout

```
skills/agentic-graph/
├── SKILL.md                  # the instruction file the agent loads
├── reference/
│   ├── spec-digest.md        # ~600-line condensation of SPEC.md
│   ├── field-reference.md    # every field, one line each
│   ├── expressions.md        # copy of docs/expressions.md
│   └── tier-guide.md         # how to choose an intelligence tier
├── schema/
│   └── agentic-graph-1.0.schema.json
├── templates/
│   ├── minimal.agraph.yaml
│   ├── phased-project.agraph.yaml
│   └── review-loop.agraph.yaml
└── scripts/
    ├── validate.py           # tools/validate_agraph.py, vendored
    ├── plan.py               # render a graph as a readable plan
    └── run.py                # optional: execute a graph
```

### Progressive disclosure

The single biggest determinant of whether this skill works is **how much you put in `SKILL.md`**.

- `SKILL.md` should be **under ~300 lines** and always loaded when the skill activates. It contains
  the mental model, the authoring procedure, the ten fields that matter, and pointers.
- `reference/` files are loaded **on demand**, when the agent needs a detail. Do not inline the
  1,900-line SPEC.md; an agent that has spent its context on the spec has none left for the project
  it is decomposing.
- `schema/` is read by `scripts/validate.py`, not by the model.

The agent should be told explicitly: *write the graph first from the templates and the field
reference; only open `spec-digest.md` when the validator reports something you do not understand.*

## 3. `SKILL.md`

Most harnesses use YAML front matter with at minimum a name and a description. The **description is
the routing decision** — it is usually the only thing in the model's context when deciding whether
to load the skill, so it must name the situations, not the technology.

```markdown
---
name: agentic-graph
version: 1.0.0
description: >
  Decompose a project or multi-step goal into an Agentic Graph (AGS 1.0) — a validated,
  reviewable DAG of agentic tasks with typed inputs and outputs, machine-checkable success
  criteria, per-task intelligence tiers, budgets, and human approval gates. Use when the
  user asks to plan, decompose, break down, or scope a project into tasks; when they ask
  for a task graph, execution plan, or work breakdown they can review before it runs; or
  when they hand you a .agraph.yaml or .agraph.json file to validate, explain, or execute.
tools_required: [file_read, file_write, shell_exec]
trigger_keywords:
  [agentic graph, agraph, ags, task graph, decompose, work breakdown, execution plan]
---

# Agentic Graph (AGS 1.0)

## Mental model

An Agentic Graph is a DAG. Each node is one agentic loop: a task an agent runs end to end.
Each edge is a control-flow dependency. The graph is the plan, written down, so a human can
approve it before anything runs.

Every node answers five questions:
  1. What must be accomplished?        -> title, description
  2. What does it get, what must it produce?  -> inputs, outputs
  3. How do we know it is done?        -> success.criteria
  4. How capable must the model be?    -> intelligence.tier
  5. What may it touch and spend?      -> requirements, constraints

If you cannot answer 3 for a node, the node is not scoped yet. Split it or sharpen it.

## Authoring procedure

1. Restate the goal in one paragraph. That is `objective`. If it needs two, it is two graphs.
2. List the units of work. A unit is one agent sitting down and finishing something. Aim for
   5-15 nodes; more than 20 means a `subgraph` is hiding in there.
3. Draw dependencies with `depends_on`. Anything not connected can run in parallel — say so
   rather than serializing it by habit.
4. For each node write `success.criteria`. Prefer `command`. Reach for `llm_judge` only when
   quality genuinely is not mechanically checkable, and always pair it with something
   deterministic.
5. Assign `intelligence.tier` per the tier guide. Justify `advanced` and `frontier` in
   `rationale`. Most nodes are `standard`.
6. Add `gate` nodes before anything expensive or irreversible, and a `human` checkpoint at
   `before_side_effects` on anything that writes outside the workspace.
7. Add budgets: node `constraints`, and graph `constraints.max_cost_usd`.
8. Validate. Repair. Repeat until clean under `--strict`.
9. Show the user the plan and the projected cost. Do not execute until they approve.

## Fields you will use constantly

  ags_version, kind, id, title, objective, entrypoints, nodes, edges
  node: type, title, description, depends_on, inputs, outputs, success,
        intelligence, requirements, constraints, failure, human, estimate
  criterion kinds: command | file_exists | artifact_present | json_schema |
                   regex | expression | llm_judge | human | external
  tiers: minimal < standard < advanced < frontier

Full list: reference/field-reference.md. Expressions: reference/expressions.md.

## Validate before you show anyone

    python3 scripts/validate.py --strict path/to/graph.agraph.yaml

Findings come back as CODE: message at JSON-Pointer. Fix every error. Fix the warnings too:
they are the exact mistakes graph generators make.

  AG902  a node that changes things has no success criteria
  AG904  a node produces an output nobody reads
  AG905  a frontier-tier node with no justification
  AG906  success rests entirely on a judge or a human with no deterministic check
  AG201  a node reads an output from a node that has not run yet

## Rules

- Never invent a model name. Capability is a tier; the harness routes it.
- Never put a secret value in a graph. Declare the name under `secrets` and reference it
  from `requirements.secrets`.
- Graphs are acyclic. Repetition is a `loop` node with `max_iterations`, never a back-edge.
- Bound everything: `max_iterations` on loops, `max_items` on maps, a cost ceiling on the graph.
- Do not execute a graph the user has not seen.

## When you need more

  reference/tier-guide.md      choosing between standard / advanced / frontier
  reference/expressions.md     the AGX expression language
  reference/spec-digest.md     everything else, condensed
  templates/                   start here rather than from an empty file
```

## 4. `reference/tier-guide.md`

Tier selection is where a generating agent is least reliable — it inflates. Give it a decision
procedure rather than adjectives.

```markdown
Ask two questions.

Q1. How much of the answer is determined by the instruction?
    Fully determined, mechanical            -> minimal
    Clear instruction, known pattern        -> standard
    Requires judgement to resolve ambiguity -> advanced or frontier

Q2. How expensive is an undetected mistake?
    A test will catch it                    -> drop one tier from Q1
    Silent, discovered weeks later          -> raise one tier
    Irreversible or externally visible      -> raise one tier, add a gate

Calibration:
  minimal   run a fixed command; rename a symbol; reformat; extract a known field
  standard  implement a specified function; write tests for a documented API; draft docs
  advanced  root-cause a failure across files; design a module interface; review a design
  frontier  choose a public API; threat-model a system; final review before an irreversible act

Sanity check: in a 12-node graph, roughly 1 frontier, 2-3 advanced, most standard, and the
mechanical nodes minimal. If you wrote more than two frontier nodes, you inflated. If you wrote
none and the graph makes an architectural decision, you underspent.

Always write `rationale` for advanced and frontier. If you cannot articulate why a smaller model
would fail, it would not.
```

## 5. `scripts/`

**`validate.py`** — vendor [`tools/validate_agraph.py`](../tools/validate_agraph.py). Two things
matter for skill use:

- **Machine-readable output.** Add a `--json` mode emitting `{code, severity, message, pointer}`
  objects. An agent repairing a graph from prose findings is doing avoidable work.
- **Exit codes.** `0` clean, `1` errors, `2` warnings under `--strict`. Skills routinely run this in
  a loop.

**`plan.py`** — render a validated graph for a human: nodes in topological order with tier and
estimate, what runs in parallel, where the gates are, projected cost, worst-case execution count.
This is what the agent shows before asking for approval, and it is the single highest-value script
in the bundle.

**`run.py`** — optional. If the harness has native AGS execution, this should shell out to it. If
not, a skill-level executor supporting conformance level 1 (task and gate nodes, `depends_on`,
`join: all`, `command`/`file_exists` criteria, sequential) is roughly 400 lines and genuinely useful.
Do not attempt level 3 in a skill.

## 6. Templates

Templates do more for output quality than instructions do. Ship at least three:

- **`minimal.agraph.yaml`** — copy of [`examples/minimal.agraph.yaml`](../examples/minimal.agraph.yaml).
  Two nodes and a gate.
- **`phased-project.agraph.yaml`** — the shape most real work takes: investigate → design →
  approval gate → parallel implementation → verify → decision → remediate-or-ship → final gate.
  Trim [`examples/library-v1-release.agraph.yaml`](../examples/library-v1-release.agraph.yaml).
- **`review-loop.agraph.yaml`** — a bounded `loop` with an exit condition, from
  [`examples/test-repair-loop.agraph.yaml`](../examples/test-repair-loop.agraph.yaml).

Keep templates *validating*. A template that fails `--strict` teaches the pattern it contains.

## 7. Two-pass generation

Single-pass generation of a fully-specified 12-node graph reliably produces vague criteria: the
model spends its attention on structure and fills `success` with "the code works". Instruct the
skill to generate in two passes:

**Pass 1 — skeleton.** `id`, `title`, `objective`, and for each node: `title`, `description`,
`depends_on`, `outputs`. Nothing else. Validate structure and topology.

**Pass 2 — specification.** For each node *individually*, given only that node plus its inputs and
outputs, generate `success.criteria`, `intelligence`, `requirements`, `constraints`, `failure` and
`estimate`.

Pass 2 is per-node and therefore parallelizable if the harness supports subagents. It is also where
criteria stop being decorative, because the model is looking at one task instead of twelve.

## 8. Integration points to negotiate with the harness

A skill can go a long way alone, but four things it cannot invent:

| Need | Why the harness must provide it |
| --- | --- |
| Model routing by tier | A skill cannot choose the model for a subsequent turn. Until the harness routes, record the tier and note in the run record that routing was not honored. |
| Human checkpoints | Needs a real channel to a person and the ability to suspend. A skill can prompt in-session; it cannot hold for two days. |
| Budget enforcement | Token and cost ceilings are harness accounting. A skill can only estimate. |
| Isolation | `worktree`, `sandbox` and `container` are harness capabilities. |

The honest posture: **be explicit about what is not enforced.** A skill that runs a `frontier` node
on whatever model happens to be loaded, and says so in the run record, is fine. One that silently
does the same is not.

## 9. Testing the skill

- **Triggering.** Ten prompts that should load it ("break this project into tasks", "plan the
  migration", "validate this agraph file") and ten that should not ("write a function", "what does
  this file do"). Measure both directions; over-triggering burns context on every unrelated turn.
- **Output validity.** Generate graphs for five different project descriptions and require every
  one to pass `--strict` within three repair iterations.
- **Criteria quality.** Sample generated `success` blocks and count what fraction of required
  criteria are `command`, `file_exists`, `expression` or `json_schema` rather than `llm_judge` or
  `human`. Below about half means pass 2 is not working.
- **Tier distribution.** Check the histogram against the calibration in the tier guide.
- **Round trip.** Validate, save, reload, re-validate; extensions and formatting must survive.

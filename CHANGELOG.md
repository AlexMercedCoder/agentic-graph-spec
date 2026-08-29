# Changelog

All notable changes to the Agentic Graph Specification are recorded here.

This project follows the versioning policy in [SPEC.md §21](SPEC.md#21-versioning-and-compatibility):

- `ags_version` is `MAJOR.MINOR` of the specification's **data model**.
- MINOR releases are backward compatible: new optional fields, new gated enum values, new advisory
  validation rules, relaxed constraints. Never a removal, a rename, a new required field, a narrowed
  enum, or a changed default.
- MAJOR releases may break anything and get a new schema `$id`.
- Repository releases use their own semantic version; a repository patch release (documentation,
  validator fixes, examples) never changes `ags_version`.

The format of this file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.0.3] — 2026-08-28

- Added a Java 17 support library with strict YAML/JSON parsing, embedded schema and semantic
  validation, AGX parsing, RFC 8785 identities, deterministic planning, and an executable CLI.
- Added shared-corpus Java tests, compiler linting, Javadocs, SpotBugs, and Maven package checks.
- Published the signed Java artifacts to Maven Central and added an opt-in release profile.

- Added a Rust 1.85+ support crate with YAML/JSON parsing, duplicate-key rejection, embedded
  schema and semantic validation, AGX parsing, RFC 8785 graph identities, effective-edge and
  topological-order helpers, deterministic Level 0 planning, and the `ags-validate` CLI.
- Added shared-corpus Rust tests, strict Clippy and rustdoc gates, MSRV verification, package
  verification, and dependency vulnerability auditing.
- Added a consolidated support-library guide covering Python, TypeScript, Go, Rust, and Java.

## [1.0.2] — 2026-08-28

- Added the `agentic-graph-spec` npm package under `typescript/` with YAML/JSON parsing, duplicate-key
  rejection, JSON Schema and semantic diagnostics, RFC 8785 digests, AGX parsing, deterministic
  Level 0 planning, TypeScript declarations, and ESM/CommonJS entry points.
- Added cross-language digest vectors, fixture-driven TypeScript tests, Node 20 CI, CLI validation,
  production dependency auditing, and packed-distribution smoke coverage.
- Added the root Go module and `ags-validate` command with Go 1.26 support, embedded schema
  validation, the complete AGS diagnostic catalogue, AGX parsing, RFC 8785 identity, deterministic
  Level 0 planning, race-tested conformance coverage, and Go vulnerability scanning.

## [1.0.1] — 2026-08-27

Normative errata and standards-hardening release. The document version remains `ags_version: "1.0"`.

- Adopted RFC 8785 JCS for cross-language graph digests and added test vectors.
- Corrected YAML parsing to YAML 1.2 Boolean semantics.
- Resolved the closed-schema/forward-minor contradiction by requiring unsupported versions to fail closed.
- Aligned AGX equality prose and made extension acceptance consistent across graph and run-record objects.
- Added governance, security reporting, versioning, implementation reports, and a distributable Python support package.

## [1.0.0] — 2026-08-09

Initial draft standard. `ags_version: "1.0"`.

### Added — data model

- **Graph object**: `ags_version`, `kind`, `id`, `title`, `objective`, `description`, `version`,
  `requires_conformance`, `authors`, `created_at`, `updated_at`, `labels`, `params`, `context`,
  `attachments`, `secrets`, `entrypoints`, `defaults`, `nodes`, `edges`, `subgraphs`, `constraints`,
  `policy`, `outputs`, `success`, `metadata`.
- **Node types**: `task`, `decision`, `gate`, `loop`, `map`, `subgraph`.
- **Node fields**: `title`, `description`, `rationale`, `instructions`, `labels`, `depends_on`,
  `join` / `join_count`, `inputs`, `outputs`, `success`, `intelligence`, `requirements`,
  `constraints`, `failure`, `human`, `when`, `estimate`, `metadata`.
- **Edges**: kinds `sequence`, `conditional`, `on_failure`, with `when`, `label`, `description` and
  documentation-only `carries`. `depends_on` defined as sugar desugaring into the effective edge set.
- **Success conditions**: `success` blocks with `mode` (`all` / `any` / `n_of`),
  `evaluation_order`, and criteria of kind `command`, `file_exists`, `artifact_present`,
  `json_schema`, `regex`, `expression`, `llm_judge`, `human`, `external`. Human-readable
  `description` required on every criterion; `severity: advisory` for non-gating checks.
- **Intelligence tiers**: `minimal` / `standard` / `advanced` / `frontier` with numeric `level`
  mirror, `hints`, `min_context_tokens`, `allow_downgrade`, `escalate_to`, `rationale`, and
  normative routing rules including the refusal case.
- **Requirements**: logical `tools` with `optional` and `alternatives`, `scope:action[:target]`
  `permissions`, `mcp_servers`, `skills`, `environment`, `secrets`, `network`, `workspace`.
- **Constraints**: token / cost / wall-clock / tool-call / agent-step ceilings, `temperature`,
  `top_p`, `seed`, `determinism`, `isolation`, `concurrency_group`, `deadline`; and graph-level
  `max_parallel_nodes`, `max_node_executions`, `max_subgraph_depth`.
- **Failure handling**: failure classes, `retry` (with `retry_on`, `feedback` and
  `escalate_intelligence`), ordered `fallback` strategies, `escalation`, `on_exhausted`,
  `compensation`, `timeout_action`.
- **Human in the loop**: `gate` nodes and `human[]` checkpoints at `before_start`,
  `before_side_effects`, `after_outputs`, `on_criteria_failure`, `on_failure`, `on_escalation`, in
  modes `approve`, `review`, `input`, `notify`.
- **Iteration and composition**: bounded `loop` (`while` / `until` / `repeat` with required
  `max_iterations`, `carry`, `collect`), bounded `map` (required `max_items`, `max_parallel`,
  `on_item_failure`, `collect`), and `subgraph` via `use`, `inline` or `ref` with integrity
  verification.
- **AGX expression language**: two syntactic positions, scope namespaces, strict typing, a fixed
  pure function set, and the prohibition on referencing secrets.

### Added — execution semantics

- Phase model `LOAD → VALIDATE → PLAN → INITIALIZE → SCHEDULE ⇄ EXECUTE → FINALIZE`.
- Node state machine with terminal states `succeeded`, `failed`, `skipped`, `cancelled`, `blocked`.
- Edge activation table, readiness and skip-propagation rules per join mode.
- Normative deterministic scheduling tie-break: topological order, then declaration order.
- Node execution sequence, including once-only input resolution and criteria-gated success.
- Termination statuses `succeeded`, `partial`, `failed`, `cancelled`, `awaiting_human`, and
  digest-guarded resumption.

### Added — conformance, validation and versioning

- Conformance levels 0 (Reader), 1 (Minimal), 2 (Standard), 3 (Full), with `requires_conformance`
  negotiation and the requirement to reject rather than degrade.
- Validation catalogue: `AG0xx` structural, `AG1xx` referential, `AG2xx`/`AG3xx` semantic,
  `AG9xx` advisory; and `RTxx` runtime diagnostics.
- Versioning and compatibility policy, deprecation policy, and extension-promotion policy.
- `x-` extension mechanism with preservation requirements.
- Security considerations covering prompt injection, permission intersection, secret handling,
  command criteria, external references, resource exhaustion and fan-out amplification.

### Added — repository

- `schema/agentic-graph-1.0.schema.json` — JSON Schema (draft 2020-12) for graph documents.
- `schema/agentic-graph-run-1.0.schema.json` — JSON Schema for run records.
- `examples/minimal.agraph.yaml` — smallest useful graph; the conformance level 1 surface.
- `examples/library-v1-release.agraph.yaml` and `.agraph.json` — canonical example, identical in
  both serializations.
- `examples/test-repair-loop.agraph.yaml` — bounded iteration.
- `examples/docs-site-refresh.agraph.yaml` and `examples/link-audit.agraph.yaml` — `map` fan-out and
  all three subgraph forms.
- `tools/validate_agraph.py` — reference validator implementing all three layers plus advisories,
  including an AGX parser.
- `tools/test_schema.py` — 55 behavior cases asserting the schema matches the specification.
- `tools/run_checks.sh` — repository self-check.
- `conformance/invalid/` — fixtures with `# EXPECT:` headers naming the diagnostic each must produce.
- `docs/expressions.md`, `docs/harness-integration.md`, `docs/skill-authoring.md`,
  `docs/design-rationale.md`, `GLOSSARY.md`.

[Unreleased]: https://github.com/AlexMercedCoder/agentic-graph-spec/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/AlexMercedCoder/agentic-graph-spec/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/AlexMercedCoder/agentic-graph-spec/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/AlexMercedCoder/agentic-graph-spec/releases/tag/v1.0.0

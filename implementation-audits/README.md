# Harness upgrade audit for OAP 1.0.1 and AGS 1.0.1

Audit date: 2026-08-27.

This is the shared work list for bringing Loro, MagAgent, and Merced-AI up to Open Agent Profile 1.0 maintenance release 1.0.1 and Agentic Graph Specification 1.0 maintenance release 1.0.1. A checked-in implementation or passing private suite is not by itself a conformance claim. Completion requires the upstream fixtures, machine-readable conformance result, and exact maintenance-release revision described below.

## Common acceptance criteria

Every implementation must:

1. Pin or declare a minimum of the 1.0.1 support library instead of copying an unidentified schema or validator.
2. Parse YAML with YAML 1.2 core Boolean rules, reject duplicate keys, and preserve JSON-equivalent values.
3. Use RFC 8785 JCS for OAP and AGS digests and pass all published digest vectors.
4. Reject unsupported OAP or AGS minor and major versions rather than discarding unknown normative fields.
5. Run the upstream positive and negative fixtures at an immutable Git revision in CI.
6. Emit a result matching the relevant `conformance/result.schema.json` with no failed REQUIRED cases.
7. Record the specification maintenance release and fixture revision in release notes and runtime support metadata.

## Loro 0.16.1

Repository: https://github.com/alexmerced-oss/loro

Focused baseline: 51 OAP/AGS tests passed. All six upstream AGS examples validate. Six of seven upstream AGS negative fixtures return the expected code; the new AG131 recursive-subgraph fixture is missed.

### P0: OAP document compatibility

- Replace the legacy `apiVersion: oap/v1` model with canonical `oap: "1.0"` while providing an explicit migration reader for existing Loro profiles.
- Replace list-shaped `state` and legacy state entries (`content`) with the normative object containing summary, facts, preferences, glossary, open threads, metrics, and update timestamp.
- Move legacy `spec.writeback` into `spec.lifecycle.writeback`; align runtime subagents, memory stores, permissions, MCP servers, skill references, context, persona, history, and delta shapes with the upstream schemas.
- Change Pydantic models from unrestricted `extra="allow"` to fail-closed normative fields, retaining extension data only in `metadata.annotations`.
- Require the normative metadata description and role instructions instead of silently defaulting required behavioral identity to empty strings.
- Consume `open-agent-profile>=1.0.1,<2` or vendor byte-identical tagged schemas with provenance and an automated drift check.

Evidence: the upstream minimal profile loads, but `code-reviewer.agent.yaml` fails on persona, permission, memory, state, and other shape differences.

### P0: Digests and YAML

- Replace sorted `json.dumps` OAP digests with RFC 8785.
- Preserve Loro's useful normalization of `metadata.revision`, `metadata.updated_at`, and `metadata.trust` for spec digests; align the exact spelling and vector outputs with OAP 1.0.1.
- Remove YAML 1.1 yes/no/on/off Boolean resolvers in both OAP and AGS loaders.
- Replace the custom AGS canonical-number routine with the published `agentic-graph-spec` support API or prove byte identity over the upstream vectors.

### P0: AGS validator and schemas

- Update both bundled AGS schemas, the skill copy, and the reference validator from the immutable 1.0.1 release.
- Implement AG131 named-fragment recursion detection and external-reference recursion detection.
- Accept `x-` extensions in every closed graph and run-record object.
- Require `graph_digest` and `harness` in Level 3 run records and validate them against the updated run schema.

### P1: Conformance publication

- Replace the provisional `docs/oap-conformance.json` with `oap.conformance-result.v1`; use current Loro version, OAP maintenance release 1.0.1, immutable fixture revision, requirement IDs, and generated timestamp.
- Add the AGS conformance-result document and CI job.
- Run cross-harness golden execution traces against MagAgent for level-1 sequential execution, level-2 decision/join behavior, and level-3 loop/map/subgraph resumption.

Recommended delivery version: Loro 0.17.0 because canonical OAP migration changes persisted profile representations.

## MagAgent 0.98.0

Repository: https://github.com/AlexMercedCoder/MagAgent

Focused baseline: the existing focused OAP/AGS suite runs successfully. All six upstream AGS examples validate. Six of seven upstream negative fixtures return the expected code; AG131 is missed.

### P0: OAP schema and parsing

- Replace the 4 KB legacy vendored profile schema with the tagged OAP 1.0.1 schemas or depend on `open-agent-profile>=1.0.1,<2`.
- Remove the stale schema comment saying the upstream repository could not be discovered and record the immutable source tag and checksum.
- Align permission values and defaults with OAP. The upstream `code-reviewer` profile currently fails because MagAgent expects an older `permissions.default` dialect.
- Permit omitted `metadata.revision` with normative default 1. The upstream minimal profile currently fails because the vendored schema incorrectly requires it.
- In Markdown parsing, reject simultaneous frontmatter and body instructions. The current `setdefault` silently ignores the body instead of raising the required error.
- Apply YAML 1.2 Boolean resolution to profile and graph loaders.

### P0: Canonical digests

- Replace OAP and AGS sorted-JSON digests with RFC 8785 JCS.
- Normalize OAP spec-digest metadata by removing revision, updated timestamp, and resolver-assigned trust.
- Add cross-language vectors and migration handling for persisted run/profile digests created by older versions; never silently resume an old run under a newly computed digest.

### P0: AGS support copy

- Replace bundled schemas and `_reference_validator.py` with the 1.0.1 support library or maintain an automated byte-for-byte drift check.
- Implement AG131 named and external subgraph recursion checks.
- Add the updated extension-object and required run-record fields.
- Verify AGX equality follows the clarified rule: different JSON types are unequal for `==`/`!=`; mixed-type ordering is an evaluation error.

### P1: Conformance publication

- Regenerate `docs/oap-conformance.json`; it currently names MagAgent 0.94.0 although the repository is 0.98.0.
- Emit both standard conformance-result formats with the immutable upstream fixture revision.
- Add Loro/MagAgent golden-trace comparisons for scheduling, criteria evidence, human events, digests, and resume refusal.

Recommended delivery version: MagAgent 0.99.0 because digest migration and vendored-contract replacement affect durable artifacts.

## Merced-AI 0.2.0

Repository: https://github.com/AlexMercedCoder/merced-ai

Baseline: the full suite passes against the local OAP 1.0.1 library with 65 passed, one skipped, and 79.65% coverage. Merced-AI has no AGS runtime or AGS conformance statement.

### P0: OAP correctness

- Raise the dependency floor to `open-agent-profile>=1.0.1,<2` and record the tested maintenance release.
- Remove the duplicate insertion of `spec.role.instructions` in `assemble_system_prompt`; add an assertion that the instruction block occurs exactly once and that the complete normative prompt order is preserved.
- Recompute stored profile and spec digests under RFC 8785 and normalized spec metadata. Add explicit handling for sessions serialized with 1.0.0 digests.
- Add a machine-readable OAP conformance result. Current behavior is closest to Level 1 plus broker-specific projection; do not claim Level 2 until state delta generation, approval, retention, history, and atomic/fsynced persistence are implemented.
- Expand discovery to every declared root or publish the omitted roots. Record all drops, narrowing, and substitutions in the conformance evidence.

### P1: Native versus projected behavior

- Keep `native_oap` limited to harnesses that consume the same canonical OAP document. A profile-name CLI handoff to a harness using a divergent dialect is not native OAP.
- Requalify Loro and MagAgent adapters after their OAP 1.0.1 migrations and remove the stale compatibility note only after their standard results pass.
- Add hostile-state and prompt-order behavioral fixtures, not only schema validation.

### P2: AGS scope decision

- Either add `agentic-graph-spec>=1.0.1,<2` and implement at least Level 0 validation/planning for brokered graphs, or explicitly declare AGS unsupported. Do not imply AGS conformance merely because routed Loro or MagAgent can execute a graph.

Recommended delivery version: Merced-AI 0.3.0 for digest migration, corrected prompt assembly, and formal OAP conformance metadata.

## Cross-implementation release gate

The three upgrades are complete when:

- OAP positive profiles load identically in all three systems and produce identical profile/spec digests.
- Loro and MagAgent return every expected AG diagnostic in the upstream corpus and produce schema-valid run records.
- Loro and MagAgent execute the same deterministic fixture with identical node order, edge activations, terminal states, criteria pass/fail results, and graph digest; provider/model details may differ and must be recorded.
- Merced-AI projects one OAP profile into Loro and MagAgent without duplicating instructions or silently discarding authority-affecting fields.
- Published harness release notes link to immutable OAP and AGS 1.0.1 conformance results.

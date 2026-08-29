# Internal security review: support libraries 1.0.4

Date: 2026-08-29. Scope: the Python, TypeScript, Go, Rust, and Java AGS parsers, validators, planners, and CLIs. This is a maintainer review, not an independent security audit.

## Controls exercised

| Threat | Required behavior | Evidence |
| --- | --- | --- |
| Parser ambiguity | YAML 1.2 scalar behavior and duplicate-key rejection | Shared language tests and canonical JSON/YAML example |
| Future-version confusion | Unsupported versions fail closed with AG002 | Shared `ag002` fixture |
| Secret disclosure through AGX | `secrets.*` is rejected | Shared `ag205` fixture |
| Dataflow escape | Forward reads, undeclared params, and undeclared outputs are rejected | Shared `ag201`, `ag203`, and `ag206` fixtures |
| Graph amplification | Cycles are rejected and loop/map bounds remain schema-required | Shared `ag111` fixture plus schema tests |
| Privilege ambiguity | Requirements remain declarative and a harness must intersect them with local policy | Normative security rules; execution is outside support-library scope |
| External subgraph substitution | Integrity is defined for non-local references and missing integrity is diagnosed | Validator advisory and specification requirements |

The expanded corpus exposed and fixed an AG203 parity defect in Go, Rust, and Java. All five implementations now consume the same fixtures dynamically, reducing the chance that a new regression is only tested in one language.

## Residual risks

- These libraries validate declarations; they cannot enforce a host harness's sandbox, credential broker, network policy, or command execution.
- External reference fetching is intentionally left to harnesses and requires separate SSRF, path-containment, digest-verification, and size-limit review.
- No coverage-guided fuzzing or independent penetration test has been completed.
- Existing Loro, MagAgent, and Merced-AI results are self-declared and tied to an earlier fixture revision. They must rerun before claiming the expanded 1.0.4 corpus.

No release-blocking defect was found after the parity fix. Independent implementation and security review remain gates for advancing the specification beyond Draft.

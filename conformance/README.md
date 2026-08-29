# Conformance fixtures

Test material for implementers. Point your own validator and harness at these.

## `invalid/`

Each fixture is an otherwise-well-formed document containing exactly one defect. The first line is
a header naming the diagnostic code the document must produce:

```yaml
# EXPECT: AG111
```

A conformant validator MUST report that code for that document. It MAY report additional findings —
several fixtures trip a second rule as a side effect of the first (a cycle through an entrypoint
also trips `AG112`, for instance) — but the named code must be present.

| Fixture | Code | Rule |
| --- | --- | --- |
| `ag002-unsupported-version.agraph.yaml` | `AG002` | Validators fail closed on unsupported versions. |
| `ag111-cycle.agraph.yaml` | `AG111` | The effective edge set of a scope must be acyclic. |
| `ag112-entrypoint-incoming.agraph.yaml` | `AG112` | An entrypoint must not have incoming edges. |
| `ag113-unknown-node.agraph.yaml` | `AG113` | An edge references a node id that does not exist in its scope. |
| `ag114-unknown-dependency.agraph.yaml` | `AG114` | `depends_on` names a node that does not exist in its scope. |
| `ag116-impossible-join.agraph.yaml` | `AG116` | `join_count` exceeds the available incoming edges. |
| `ag117-reserved-node-id.agraph.yaml` | `AG117` | `self` is reserved and cannot be a node id. |
| `ag121-expression-branch-without-condition.agraph.yaml` | `AG121` | An expression-evaluated branch has no `when`. |
| `ag123-unknown-default-branch.agraph.yaml` | `AG123` | A decision default names no declared branch. |
| `ag124-duplicate-branch.agraph.yaml` | `AG124` | Decision branch labels are duplicated. |
| `ag131-recursive-subgraph.agraph.yaml` | `AG131` | Named subgraph references must not be recursive. |
| `ag132-unknown-fragment.agraph.yaml` | `AG132` | A `use` clause names no declared fragment. |
| `ag141-tier-mismatch.agraph.yaml` | `AG141` | `intelligence.tier` and `intelligence.level` must agree. |
| `ag142-downward-escalation.agraph.yaml` | `AG142` | An escalation target is below the current tier. |
| `ag201-forward-read.agraph.yaml` | `AG201` | A node may only read outputs of its transitive predecessors. |
| `ag203-undeclared-param.agraph.yaml` | `AG203` | An expression references an undeclared parameter. |
| `ag204-bad-expression.agraph.yaml` | `AG204` | An expression is syntactically invalid or calls an unknown function. |
| `ag205-secret-reference.agraph.yaml` | `AG205` | Expressions must not reference `secrets.*`. |
| `ag206-undeclared-output.agraph.yaml` | `AG206` | An expression references an undeclared node output. |
| `ag211-interpolation-in-expression.agraph.yaml` | `AG211` | An expression position incorrectly uses template delimiters. |

All five support libraries discover this directory dynamically and read the expected code from the header. Adding a fixture therefore expands the shared conformance suite without updating five hard-coded lists.

## Published results

Machine-readable, self-declared implementation results are retained in [`results/`](results/) and validated against [`result.schema.json`](result.schema.json), including the complete required evidence surface for the claimed level. Run `python tools/verify_conformance_results.py` to verify them. Results are bound to their recorded fixture Git revision and are not certifications.

Run them all:

```bash
tools/run_checks.sh
```

Or one at a time:

```bash
python3 tools/validate_agraph.py conformance/invalid/ag111-cycle.agraph.yaml
```

## Valid documents

The positive cases live in [`examples/`](../examples/). Every one must validate with **zero errors
and zero warnings** under `--strict`. In addition:

- `examples/minimal.agraph.yaml` is the conformance level 1 execution surface. A level 1 harness
  must be able to run it end to end.
- `examples/library-v1-release.agraph.yaml` and `examples/library-v1-release.agraph.json` must parse
  to identical data. A harness that treats JSON and YAML differently is not conformant.
- `examples/docs-site-refresh.agraph.yaml` references `examples/link-audit.agraph.yaml` by relative
  path, exercising external subgraph resolution.

## Contributing a fixture

One defect per file, the `# EXPECT:` header, a comment explaining the rule in one sentence, and a
row in the table above. Keep fixtures minimal — the smallest document that trips the rule.

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
| `ag111-cycle.agraph.yaml` | `AG111` | The effective edge set of a scope must be acyclic. |
| `ag113-unknown-node.agraph.yaml` | `AG113` | An edge references a node id that does not exist in its scope. |
| `ag141-tier-mismatch.agraph.yaml` | `AG141` | `intelligence.tier` and `intelligence.level` must agree. |
| `ag201-forward-read.agraph.yaml` | `AG201` | A node may only read outputs of its transitive predecessors. |
| `ag204-bad-expression.agraph.yaml` | `AG204` | An expression is syntactically invalid or calls an unknown function. |
| `ag205-secret-reference.agraph.yaml` | `AG205` | Expressions must not reference `secrets.*`. |

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

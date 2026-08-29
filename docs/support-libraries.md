# AGS support libraries

The repository maintains conformance-level-0 support libraries for Python,
TypeScript, Go, Rust, and Java. Every implementation parses and validates AGS
1.0 documents, computes the same RFC 8785 graph identity, exposes deterministic
planning helpers, and does not execute graph nodes.

| Language | Runtime | Package or module | Documentation |
| --- | --- | --- | --- |
| Python | 3.10+ | `agentic-graph-spec` | This guide and the root package `ags` |
| TypeScript | Node.js 20+ | `agentic-graph-spec` | [`typescript/README.md`](../typescript/README.md) |
| Go | 1.26+ | `github.com/AlexMercedCoder/agentic-graph-spec` | This guide and Go package comments |
| Rust | 1.85+ | `agentic-graph-spec` | [`rust/README.md`](../rust/README.md) and docs.rs |
| Java | 17+ | `io.github.alexmercedcoder:agentic-graph-spec` | [`java/README.md`](../java/README.md) and the generated Javadocs |

## Python

```console
python -m pip install agentic-graph-spec
ags-validate --strict graph.agraph.yaml
```

```python
from ags import graph_digest, validate_path

report = validate_path("graph.agraph.yaml")
if report.errors:
    raise ValueError(report.errors)
print(graph_digest(report.document))
```

## TypeScript

```console
npm install agentic-graph-spec
npx ags-validate --strict graph.agraph.yaml
```

The package provides ESM and CommonJS entry points, TypeScript declarations,
strict YAML 1.2 and JSON loaders, the complete diagnostic catalogue, AGX parsing,
and deterministic planning. See its [language README](../typescript/README.md).

## Go

```console
go get github.com/AlexMercedCoder/agentic-graph-spec@v1.0.3
```

```go
graph, err := ags.Load("graph.agraph.yaml")
if err != nil { return err }
report := ags.Validate(graph)
if !report.OK { return fmt.Errorf("invalid graph: %v", report.Errors) }
plan, err := ags.PlanGraph(graph)
```

The validator CLI is available from `cmd/ags-validate`.

## Rust

```console
cargo add agentic-graph-spec@1.0.3
cargo install agentic-graph-spec --version 1.0.3
ags-validate --strict graph.agraph.yaml
```

See the [Rust README](../rust/README.md) for the native API and MSRV policy.

## Java

```xml
<dependency>
  <groupId>io.github.alexmercedcoder</groupId>
  <artifactId>agentic-graph-spec</artifactId>
  <version>1.0.3</version>
</dependency>
```

The Java source builds a normal library JAR, source and Javadoc JARs, and an
executable `-cli.jar`. See the [Java README](../java/README.md). Maven Central
publication is pending initial namespace and signing setup.

## Conformance and maintenance

Each native implementation is tested against the shared valid and invalid
fixtures, the YAML 1.2 and duplicate-key requirements, exact cross-language
digest vectors, AGX behavior, and deterministic plans. CI also applies the
language's formatter, compiler or linter, package build, and static checks.

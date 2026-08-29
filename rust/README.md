# Agentic Graph Specification for Rust

Native Rust support for Agentic Graph Specification 1.0. The crate provides the same
conformance-level-0 surface as the Python, TypeScript, and Go libraries:

- YAML 1.2 and JSON parsing with duplicate-key rejection;
- embedded JSON Schema plus semantic and AGX dataflow validation;
- RFC 8785 canonical JSON and SHA-256 graph identities;
- AGX parsing with function-call and reference collection;
- effective-edge calculation and deterministic topological ordering;
- deterministic, non-executing Level 0 plans; and
- the `ags-validate` CLI.

The MSRV is Rust 1.85.0 and the crate uses edition 2024.

```rust
use agentic_graph_spec::{load, graph_digest, plan_graph, validate};

let graph = load("graph.agraph.yaml")?;
let report = validate(&graph);
assert!(report.ok, "{:?}", report.errors);
println!("{}", graph_digest(&graph)?);
println!("{:?}", plan_graph(&graph)?.order);
# Ok::<(), Box<dyn std::error::Error>>(())
```

```console
cargo install agentic-graph-spec --version 1.0.4
ags-validate --strict graph.agraph.yaml
```

This library validates and plans graphs; it does not execute them.

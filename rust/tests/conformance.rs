use std::path::PathBuf;

use agentic_graph_spec::{graph_digest, load, parse, parse_expression, plan_graph, validate_path};

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}

#[test]
fn accepts_valid_corpus() {
    for name in [
        "minimal.agraph.yaml",
        "library-v1-release.agraph.yaml",
        "library-v1-release.agraph.json",
        "test-repair-loop.agraph.yaml",
        "docs-site-refresh.agraph.yaml",
        "link-audit.agraph.yaml",
    ] {
        let report = validate_path(repository().join("examples").join(name));
        assert!(report.ok, "{name}: {:?}", report.errors);
    }
}

#[test]
fn rejects_invalid_corpus_with_expected_codes() {
    for (name, code) in [
        ("ag111-cycle.agraph.yaml", "AG111"),
        ("ag113-unknown-node.agraph.yaml", "AG113"),
        ("ag131-recursive-subgraph.agraph.yaml", "AG131"),
        ("ag141-tier-mismatch.agraph.yaml", "AG141"),
        ("ag201-forward-read.agraph.yaml", "AG201"),
        ("ag204-bad-expression.agraph.yaml", "AG204"),
        ("ag205-secret-reference.agraph.yaml", "AG205"),
    ] {
        let report = validate_path(repository().join("conformance/invalid").join(name));
        assert!(
            report.errors.iter().any(|finding| finding.code == code),
            "{name}: {:?}",
            report.errors
        );
    }
}

#[test]
fn canonical_identity_matches_other_libraries() {
    let yaml = load(repository().join("examples/library-v1-release.agraph.yaml")).unwrap();
    let json = load(repository().join("examples/library-v1-release.agraph.json")).unwrap();
    assert_eq!(yaml, json);
    assert_eq!(graph_digest(&yaml).unwrap(), graph_digest(&json).unwrap());
    assert_eq!(
        graph_digest(&json).unwrap(),
        "sha256-ZaKZTS3i9OBDZNnKSNF2ZI22BZmOh1CcVNM0VZGDe+A="
    );
}

#[test]
fn portable_parsing_planning_and_agx() {
    let document = parse(
        "value: yes\nenabled: true\ncreated: 2026-08-28T00:00:00Z\n",
        "yaml",
    )
    .unwrap();
    assert_eq!(document["value"], "yes");
    assert_eq!(document["enabled"], true);
    assert_eq!(document["created"], "2026-08-28T00:00:00Z");
    assert!(parse("value: 1\nvalue: 2\n", "yaml").is_err());
    assert!(parse("", "yaml").is_err());
    let graph = load(repository().join("examples/minimal.agraph.yaml")).unwrap();
    let first = plan_graph(&graph).unwrap();
    let second = plan_graph(&graph).unwrap();
    assert_eq!(first, second);
    assert!(!first.executable);
    assert_eq!(first.order.len(), graph["nodes"].as_object().unwrap().len());
    let parsed =
        parse_expression("succeeded('build') && len(nodes.build.outputs.files) > 0").unwrap();
    assert_eq!(
        parsed
            .calls
            .iter()
            .map(|call| (&*call.name, call.arity))
            .collect::<Vec<_>>(),
        [("succeeded", 1), ("len", 1)]
    );
    assert_eq!(
        parsed.references,
        [vec!["nodes", "build", "outputs", "files"]]
    );
}

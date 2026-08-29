use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    path::Path,
};

use regex::Regex;
use serde_json::Value;

use crate::{
    Document, ValidationReport, graph_effective_edges, load, object, parse_expression, strings,
};

const SCHEMA: &str = include_str!("../schema/agentic-graph-1.0.schema.json");

/// Runs embedded JSON Schema, semantic, topology, and AGX dataflow validation.
pub fn validate(document: &Document) -> ValidationReport {
    let mut report = ValidationReport::new(document.clone());
    let value = Value::Object(document.clone());
    match serde_json::from_str(SCHEMA)
        .ok()
        .and_then(|schema| jsonschema::validator_for(&schema).ok())
    {
        Some(validator) => {
            for error in validator.iter_errors(&value) {
                let pointer = error.instance_path().to_string();
                let text = error.to_string();
                let code = if text.contains("additional properties") {
                    "AG003"
                } else if text.contains("not one of") || text.contains("enum") {
                    "AG004"
                } else if pointer.contains("/edges/") && text.contains("valid") {
                    "AG103"
                } else if pointer.contains("/inputs/") && text.contains("valid") {
                    "AG104"
                } else {
                    "AG001"
                };
                report.add(code, "error", text, pointer);
            }
        }
        None => report.add(
            "AG001",
            "error",
            "embedded schema could not be compiled",
            "",
        ),
    }
    let version = document
        .get("ags_version")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let pieces: Vec<&str> = version.split('.').collect();
    if pieces.len() != 2 || pieces.iter().any(|piece| piece.parse::<u64>().is_err()) {
        report.add(
            "AG002",
            "error",
            format!("unparsable ags_version {version:?}"),
            "",
        );
    } else if pieces != ["1", "0"] {
        report.add(
            "AG002",
            "error",
            format!("unsupported AGS version {version}"),
            "",
        );
    }
    if report.errors.is_empty() {
        semantic(document, &mut report);
    }
    report.ok = report.errors.is_empty();
    report
}

/// Loads and validates an AGS document, returning parse failures as diagnostics.
pub fn validate_path(path: impl AsRef<Path>) -> ValidationReport {
    match load(path) {
        Ok(document) => validate(&document),
        Err(error) => {
            let mut report = ValidationReport {
                document: None,
                findings: vec![],
                errors: vec![],
                warnings: vec![],
                ok: false,
            };
            report.add(error.code, "error", error.to_string(), "");
            report
        }
    }
}

#[derive(Clone)]
struct Scope {
    pointer: String,
    nodes: Document,
    edges: Vec<Value>,
    entrypoints: Vec<String>,
    param_names: BTreeSet<String>,
    root: bool,
}

fn scopes(document: &Document) -> Vec<Scope> {
    fn collect(
        nodes: &Document,
        base: &str,
        inherited_params: &BTreeSet<String>,
        result: &mut Vec<Scope>,
    ) {
        for (id, raw) in nodes {
            let node = object(Some(raw));
            let kind = node.get("type").and_then(Value::as_str).unwrap_or("task");
            if !matches!(kind, "loop" | "map" | "subgraph") {
                continue;
            }
            let block = object(node.get(kind));
            let key = if kind == "subgraph" { "inline" } else { "body" };
            if let Some(fragment) = block.get(key).and_then(Value::as_object) {
                let pointer = format!("{base}/nodes/{id}/{kind}/{key}");
                let declared: BTreeSet<String> =
                    object(fragment.get("params")).keys().cloned().collect();
                let child = Scope {
                    pointer: pointer.clone(),
                    nodes: object(fragment.get("nodes")).clone(),
                    edges: fragment
                        .get("edges")
                        .and_then(Value::as_array)
                        .cloned()
                        .unwrap_or_default(),
                    entrypoints: strings(fragment.get("entrypoints")),
                    param_names: if declared.is_empty() {
                        inherited_params.clone()
                    } else {
                        declared
                    },
                    root: false,
                };
                collect(&child.nodes, &pointer, &child.param_names, result);
                result.push(child);
            }
        }
    }
    let root_params: BTreeSet<String> = object(document.get("params")).keys().cloned().collect();
    let mut result = vec![Scope {
        pointer: String::new(),
        nodes: object(document.get("nodes")).clone(),
        edges: document
            .get("edges")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default(),
        entrypoints: strings(document.get("entrypoints")),
        param_names: root_params.clone(),
        root: true,
    }];
    collect(&result[0].nodes.clone(), "", &root_params, &mut result);
    for (name, raw) in object(document.get("subgraphs")) {
        let fragment = object(Some(raw));
        let pointer = format!("/subgraphs/{name}");
        let declared: BTreeSet<String> = object(fragment.get("params")).keys().cloned().collect();
        let child = Scope {
            pointer: pointer.clone(),
            nodes: object(fragment.get("nodes")).clone(),
            edges: fragment
                .get("edges")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default(),
            entrypoints: strings(fragment.get("entrypoints")),
            param_names: if declared.is_empty() {
                root_params.clone()
            } else {
                declared
            },
            root: false,
        };
        collect(&child.nodes, &pointer, &child.param_names, &mut result);
        result.push(child);
    }
    result
}

fn scope_edges(scope: &Scope) -> Vec<(String, String)> {
    let mut edges = vec![];
    for (id, raw) in &scope.nodes {
        for dependency in strings(raw.as_object().and_then(|node| node.get("depends_on"))) {
            edges.push((dependency, id.clone()));
        }
    }
    for raw in &scope.edges {
        let edge = object(Some(raw));
        edges.push((
            edge.get("from")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            edge.get("to")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
        ));
    }
    edges
}

fn semantic(document: &Document, report: &mut ValidationReport) {
    let all_scopes = scopes(document);
    for scope in &all_scopes {
        validate_scope(scope, document, report);
    }
    validate_recursion(document, report);
    let has_estimate = all_scopes.iter().any(|scope| {
        scope
            .nodes
            .values()
            .any(|node| node.get("estimate").is_some())
    });
    if object(document.get("constraints"))
        .get("max_cost_usd")
        .is_none()
        && !has_estimate
    {
        report.add("AG908", "warning", "graph has neither constraints.max_cost_usd nor any node estimate; its cost cannot be previewed", "");
    }
    check_unread_outputs(document, &all_scopes, report);
}

fn validate_scope(scope: &Scope, document: &Document, report: &mut ValidationReport) {
    let edges = scope_edges(scope);
    let mut incoming: BTreeMap<String, usize> =
        scope.nodes.keys().map(|id| (id.clone(), 0)).collect();
    let mut direct: BTreeMap<String, Vec<String>> =
        scope.nodes.keys().map(|id| (id.clone(), vec![])).collect();
    let explicit_pairs: BTreeSet<(String, String)> = scope
        .edges
        .iter()
        .map(|raw| {
            let edge = object(Some(raw));
            (
                edge.get("from")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .into(),
                edge.get("to")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .into(),
            )
        })
        .collect();
    for raw in &scope.edges {
        let edge = object(Some(raw));
        for key in ["from", "to"] {
            let id = edge.get(key).and_then(Value::as_str).unwrap_or_default();
            if !scope.nodes.contains_key(id) {
                report.add(
                    "AG113",
                    "error",
                    format!("edge references unknown node {id:?}"),
                    &scope.pointer,
                );
            }
        }
    }
    for (id, raw) in &scope.nodes {
        for dependency in strings(raw.as_object().and_then(|node| node.get("depends_on"))) {
            if !scope.nodes.contains_key(&dependency) {
                report.add(
                    "AG114",
                    "error",
                    format!("depends_on references unknown node {dependency:?}"),
                    format!("{}/nodes/{id}", scope.pointer),
                );
            }
            if explicit_pairs.contains(&(dependency.clone(), id.clone())) {
                report.add(
                    "AG901",
                    "warning",
                    format!(
                        "{dependency} -> {id} declared by both depends_on and an explicit edge"
                    ),
                    format!("{}/nodes/{id}", scope.pointer),
                );
            }
        }
    }
    for (from, to) in &edges {
        if scope.nodes.contains_key(from) && scope.nodes.contains_key(to) {
            *incoming.get_mut(to).unwrap() += 1;
            direct.get_mut(to).unwrap().push(from.clone());
        }
    }
    if has_cycle(&scope.nodes, &edges) {
        report.add(
            "AG111",
            "error",
            "cycle in effective edge set",
            &scope.pointer,
        );
    }
    for entry in &scope.entrypoints {
        if !scope.nodes.contains_key(entry) {
            report.add(
                if scope.root { "AG115" } else { "AG133" },
                "error",
                format!("entrypoint {entry:?} is not a node in this scope"),
                &scope.pointer,
            );
        } else if incoming[entry] > 0 {
            report.add(
                "AG112",
                "error",
                format!("entrypoint {entry:?} has incoming edges"),
                &scope.pointer,
            );
        }
    }
    let mut reachable = BTreeSet::new();
    let mut queue: VecDeque<String> = scope.entrypoints.iter().cloned().collect();
    let mut outgoing: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (from, to) in &edges {
        outgoing.entry(from.clone()).or_default().push(to.clone());
    }
    while let Some(id) = queue.pop_front() {
        if reachable.insert(id.clone()) {
            queue.extend(outgoing.get(&id).into_iter().flatten().cloned());
        }
    }
    for id in scope.nodes.keys().filter(|id| !reachable.contains(*id)) {
        report.add(
            "AG903",
            "warning",
            format!("node {id:?} is unreachable from any entrypoint"),
            format!("{}/nodes/{id}", scope.pointer),
        );
    }
    let predecessors = transitive_predecessors(&scope.nodes, &direct);
    let mut ids: Vec<_> = scope.nodes.keys().cloned().collect();
    ids.sort();
    for id in ids {
        validate_node(
            scope,
            document,
            &id,
            incoming.get(&id).copied().unwrap_or(0),
            predecessors.get(&id).unwrap(),
            report,
        );
    }
}

fn walk_all_strings(value: &Value, visit: &mut impl FnMut(&str)) {
    match value {
        Value::String(text) => visit(text),
        Value::Array(items) => {
            for item in items {
                walk_all_strings(item, visit);
            }
        }
        Value::Object(map) => {
            for item in map.values() {
                walk_all_strings(item, visit);
            }
        }
        _ => {}
    }
}

fn check_unread_outputs(document: &Document, scopes: &[Scope], report: &mut ValidationReport) {
    let external = Regex::new(r"nodes\.([A-Za-z_][\w-]*)\.outputs\.([A-Za-z_][\w-]*)").unwrap();
    let own = Regex::new(r"(?:self|nodes\.self)\.outputs\.([A-Za-z_][\w-]*)").unwrap();
    let mut reads = BTreeSet::new();
    walk_all_strings(&Value::Object(document.clone()), &mut |text| {
        for capture in external.captures_iter(text) {
            reads.insert((capture[1].to_owned(), capture[2].to_owned()));
        }
    });
    for scope in scopes {
        for (id, raw) in &scope.nodes {
            walk_all_strings(raw, &mut |text| {
                for capture in own.captures_iter(text) {
                    reads.insert((id.clone(), capture[1].to_owned()));
                }
            });
            for name in object(raw.get("outputs")).keys() {
                if !reads.contains(&(id.clone(), name.clone())) {
                    report.add(
                        "AG904",
                        "warning",
                        format!("output {name:?} of node {id:?} is never read"),
                        format!("{}/nodes/{id}/outputs/{name}", scope.pointer),
                    );
                }
            }
        }
    }
}

fn has_cycle(nodes: &Document, edges: &[(String, String)]) -> bool {
    let mut incoming: BTreeMap<_, usize> = nodes.keys().map(|id| (id.clone(), 0)).collect();
    let mut outgoing: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (from, to) in edges {
        if incoming.contains_key(from) && incoming.contains_key(to) {
            *incoming.get_mut(to).unwrap() += 1;
            outgoing.entry(from.clone()).or_default().push(to.clone());
        }
    }
    let mut queue: VecDeque<_> = incoming
        .iter()
        .filter(|(_, n)| **n == 0)
        .map(|(id, _)| id.clone())
        .collect();
    let mut seen = 0;
    while let Some(id) = queue.pop_front() {
        seen += 1;
        for target in outgoing.get(&id).into_iter().flatten() {
            let count = incoming.get_mut(target).unwrap();
            *count -= 1;
            if *count == 0 {
                queue.push_back(target.clone());
            }
        }
    }
    seen != nodes.len()
}

fn transitive_predecessors(
    nodes: &Document,
    direct: &BTreeMap<String, Vec<String>>,
) -> BTreeMap<String, BTreeSet<String>> {
    let mut result = BTreeMap::new();
    for id in nodes.keys() {
        let mut seen = BTreeSet::new();
        let mut stack = direct.get(id).cloned().unwrap_or_default();
        while let Some(parent) = stack.pop() {
            if seen.insert(parent.clone()) {
                stack.extend(direct.get(&parent).cloned().unwrap_or_default());
            }
        }
        result.insert(id.clone(), seen);
    }
    result
}

fn validate_node(
    scope: &Scope,
    document: &Document,
    id: &str,
    incoming: usize,
    predecessors: &BTreeSet<String>,
    report: &mut ValidationReport,
) {
    let node = object(scope.nodes.get(id));
    let pointer = format!("{}/nodes/{id}", scope.pointer);
    let kind = node.get("type").and_then(Value::as_str).unwrap_or("task");
    if id == "self" {
        report.add(
            "AG117",
            "error",
            "'self' is a reserved namespace root and cannot be a node id",
            &pointer,
        );
    }
    for other in ["loop", "map", "subgraph", "gate", "decision"] {
        if other != kind && node.contains_key(other) {
            report.add(
                "AG101",
                "error",
                format!("node of type {kind:?} declares a {other:?} block"),
                &pointer,
            );
        }
    }
    if kind == "gate" && node.contains_key("intelligence") {
        report.add(
            "AG102",
            "error",
            "gate nodes must not declare intelligence",
            &pointer,
        );
    }
    if matches!(kind, "decision" | "gate") && object(node.get("outputs")).contains_key("decision") {
        report.add(
            "AG122",
            "error",
            "'decision' is a reserved output name on decision and gate nodes",
            &pointer,
        );
    }
    if node.get("join").and_then(Value::as_str) == Some("n_of")
        && node.get("join_count").and_then(Value::as_u64).unwrap_or(0) as usize > incoming
    {
        report.add(
            "AG116",
            "error",
            "join_count exceeds incoming edges",
            &pointer,
        );
    }
    let intel = object(node.get("intelligence"));
    let tier = intel
        .get("tier")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let rank = |name: &str| match name {
        "minimal" => 1,
        "standard" => 2,
        "advanced" => 3,
        "frontier" => 4,
        _ => 0,
    };
    if let Some(level) = intel.get("level").and_then(Value::as_u64) {
        if !tier.is_empty() && rank(tier) != level {
            report.add(
                "AG141",
                "error",
                "intelligence tier and level disagree",
                &pointer,
            );
        }
    }
    if let Some(target) = intel.get("escalate_to").and_then(Value::as_str) {
        if rank(target) < rank(tier) {
            report.add(
                "AG142",
                "error",
                "escalate_to is below the configured tier",
                &pointer,
            );
        }
    }
    if tier == "frontier"
        && intel
            .get("rationale")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .is_empty()
    {
        report.add(
            "AG905",
            "warning",
            "frontier-tier node has no rationale",
            &pointer,
        );
    }
    if matches!(kind, "loop" | "map" | "subgraph") {
        let block = object(node.get(kind));
        if let Some(used) = block.get("use").and_then(Value::as_str) {
            if !object(document.get("subgraphs")).contains_key(used) {
                report.add(
                    "AG132",
                    "error",
                    format!("{kind}.use names unknown fragment {used:?}"),
                    &pointer,
                );
            }
        }
        let reference = object(block.get("ref"));
        if let Some(uri) = reference.get("uri").and_then(Value::as_str) {
            if !uri.starts_with('.')
                && !uri.starts_with('/')
                && !reference.contains_key("integrity")
            {
                report.add(
                    "AG909",
                    "warning",
                    "non-local subgraph reference has no integrity digest",
                    &pointer,
                );
            }
        }
    }
    if kind == "decision" {
        let decision = object(node.get("decision"));
        let mut labels: BTreeMap<String, usize> = BTreeMap::new();
        for (index, raw) in decision
            .get("branches")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let branch = object(Some(raw));
            let label = branch
                .get("label")
                .and_then(Value::as_str)
                .unwrap_or_default();
            *labels.entry(label.into()).or_insert(0) += 1;
            if decision.get("evaluator").and_then(Value::as_str) == Some("expression")
                && !branch.contains_key("when")
            {
                report.add(
                    "AG121",
                    "error",
                    format!("branch {label:?} has no 'when' but evaluator is 'expression'"),
                    format!("{pointer}/decision/branches/{index}"),
                );
            }
        }
        let duplicates: Vec<_> = labels
            .iter()
            .filter(|(_, count)| **count > 1)
            .map(|(label, _)| label.clone())
            .collect();
        if !duplicates.is_empty() {
            report.add(
                "AG124",
                "error",
                format!("duplicate branch labels {duplicates:?}"),
                &pointer,
            );
        }
        if let Some(default) = decision.get("default_branch").and_then(Value::as_str) {
            if !labels.contains_key(default) {
                report.add(
                    "AG123",
                    "error",
                    format!("default_branch {default:?} is not a declared label"),
                    &pointer,
                );
            }
        }
    }
    let outputs = object(node.get("outputs"));
    let failure = object(node.get("failure"));
    for (index, raw) in failure
        .get("fallback")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .enumerate()
    {
        let step = object(Some(raw));
        let location = format!("{pointer}/failure/fallback/{index}");
        match step
            .get("strategy")
            .and_then(Value::as_str)
            .unwrap_or_default()
        {
            "alternate_node" => {
                let alternate = step.get("node").and_then(Value::as_str).unwrap_or_default();
                if let Some(target) = scope.nodes.get(alternate) {
                    let available = declared_outputs(object(Some(target)));
                    let missing: Vec<_> = outputs
                        .iter()
                        .filter(|(_, spec)| {
                            object(Some(spec))
                                .get("required")
                                .and_then(Value::as_bool)
                                .unwrap_or(true)
                        })
                        .filter(|(name, _)| !available.contains(*name))
                        .map(|(name, _)| name.clone())
                        .collect();
                    if !missing.is_empty() {
                        report.add("AG151", "error", format!("fallback node {alternate:?} does not declare required outputs {missing:?}"), &location);
                    }
                } else {
                    report.add(
                        "AG113",
                        "error",
                        format!("fallback node {alternate:?} does not exist"),
                        &location,
                    );
                }
            }
            "relax_criteria" => {
                let declared: BTreeSet<_> = object(node.get("success"))
                    .get("criteria")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(|criterion| {
                        object(Some(criterion)).get("id").and_then(Value::as_str)
                    })
                    .collect();
                let unknown: Vec<_> = strings(step.get("criteria"))
                    .into_iter()
                    .filter(|name| !declared.contains(name.as_str()))
                    .collect();
                if !unknown.is_empty() {
                    report.add(
                        "AG153",
                        "error",
                        format!("unknown criteria {unknown:?}"),
                        &location,
                    );
                }
            }
            "degrade_outputs" => {
                let unknown: Vec<_> = strings(step.get("outputs"))
                    .into_iter()
                    .filter(|name| !outputs.contains_key(name))
                    .collect();
                if !unknown.is_empty() {
                    report.add(
                        "AG153",
                        "error",
                        format!("unknown outputs {unknown:?}"),
                        &location,
                    );
                }
            }
            _ => {}
        }
    }
    if let Some(compensation) = failure.get("compensation").and_then(Value::as_str) {
        if let Some(target) = scope.nodes.get(compensation) {
            if object(object(Some(target)).get("failure")).contains_key("compensation") {
                report.add(
                    "AG152",
                    "error",
                    format!("compensation node {compensation:?} declares its own compensation"),
                    &pointer,
                );
            }
        } else {
            report.add(
                "AG113",
                "error",
                format!("compensation node {compensation:?} does not exist"),
                &pointer,
            );
        }
    }
    let escalation = object(failure.get("escalation"));
    if escalation.get("to").and_then(Value::as_str) == Some("node") {
        let target = escalation
            .get("node")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if !scope.nodes.contains_key(target) {
            report.add(
                "AG113",
                "error",
                format!("escalation node {target:?} does not exist"),
                &pointer,
            );
        }
    }
    let requirements = object(node.get("requirements"));
    let mut mutating = requirements.get("workspace").and_then(Value::as_str) == Some("read_write");
    for permission in strings(requirements.get("permissions")) {
        mutating |= [
            "fs:write",
            "fs:delete",
            "git:commit",
            "git:push",
            "shell:exec",
        ]
        .iter()
        .any(|prefix| permission.starts_with(prefix));
    }
    if mutating && !node.contains_key("success") && kind == "task" {
        report.add(
            "AG902",
            "warning",
            "side-effecting node declares no success block",
            &pointer,
        );
    }
    let success = object(node.get("success"));
    let required_kinds: Vec<_> = success
        .get("criteria")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|raw| {
            let criterion = object(Some(raw));
            let severity = criterion
                .get("severity")
                .and_then(Value::as_str)
                .unwrap_or("required");
            (severity == "required").then(|| {
                criterion
                    .get("kind")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
            })
        })
        .collect();
    if !required_kinds.is_empty()
        && required_kinds
            .iter()
            .all(|kind| matches!(*kind, "llm_judge" | "human"))
    {
        report.add(
            "AG906",
            "warning",
            "success block has no deterministic required criterion",
            &pointer,
        );
    }
    let constraints = object(node.get("constraints"));
    if constraints.get("determinism").and_then(Value::as_str) == Some("strict")
        && !constraints.contains_key("seed")
    {
        report.add(
            "AG907",
            "warning",
            "determinism 'strict' without a seed",
            &pointer,
        );
    }
    walk_expressions(
        Value::Object(node.clone()),
        &pointer,
        "",
        scope,
        id,
        predecessors,
        report,
    );
}

fn walk_expressions(
    value: Value,
    pointer: &str,
    key: &str,
    scope: &Scope,
    node_id: &str,
    predecessors: &BTreeSet<String>,
    report: &mut ValidationReport,
) {
    match value {
        Value::Object(map) => {
            for (child_key, child) in map {
                if child_key != "body" && child_key != "inline" {
                    walk_expressions(
                        child,
                        &format!("{pointer}/{child_key}"),
                        &child_key,
                        scope,
                        node_id,
                        predecessors,
                        report,
                    );
                }
            }
        }
        Value::Array(items) => {
            for (index, item) in items.into_iter().enumerate() {
                walk_expressions(
                    item,
                    &format!("{pointer}/{index}"),
                    key,
                    scope,
                    node_id,
                    predecessors,
                    report,
                );
            }
        }
        Value::String(text) => {
            let expression = matches!(
                key,
                "from" | "when" | "expr" | "target" | "condition" | "over"
            );
            if expression {
                validate_expression(&text, pointer, scope, node_id, predecessors, report);
            } else {
                for inner in template_expressions(&text) {
                    validate_expression(inner, pointer, scope, node_id, predecessors, report);
                }
            }
        }
        _ => {}
    }
}

fn template_expressions(text: &str) -> Vec<&str> {
    let mut out = vec![];
    let mut rest = text;
    while let Some(start) = rest.find("${{") {
        rest = &rest[start + 3..];
        if let Some(end) = rest.find("}}") {
            out.push(rest[..end].trim());
            rest = &rest[end + 2..];
        } else {
            break;
        }
    }
    out
}

fn validate_expression(
    text: &str,
    pointer: &str,
    scope: &Scope,
    node_id: &str,
    predecessors: &BTreeSet<String>,
    report: &mut ValidationReport,
) {
    if text.contains("${{") {
        report.add(
            "AG211",
            "error",
            "'${{ }}' interpolation used in expression position",
            pointer,
        );
        return;
    }
    if text.trim().is_empty() {
        return;
    }
    let parsed = match parse_expression(text) {
        Ok(parsed) => parsed,
        Err(error) => {
            report.add(
                "AG204",
                "error",
                format!("invalid expression: {error}"),
                pointer,
            );
            return;
        }
    };
    for call in parsed.calls {
        let allowed = match call.name.as_str() {
            "get" => (2, 3),
            "len" | "count" | "lower" | "upper" | "trim" | "int" | "float" | "bool" | "str"
            | "json" | "any" | "all" | "succeeded" | "failed" | "skipped" => (1, 1),
            "contains" | "startswith" | "endswith" | "matches" | "split" | "join" | "default"
            | "output" => (2, 2),
            _ => {
                report.add(
                    "AG204",
                    "error",
                    format!("unknown function {:?}", call.name),
                    pointer,
                );
                continue;
            }
        };
        if call.arity < allowed.0 || call.arity > allowed.1 {
            report.add(
                "AG204",
                "error",
                format!("function {} received {} argument(s)", call.name, call.arity),
                pointer,
            );
        }
    }
    for parts in parsed.references {
        if parts.first().is_some_and(|part| part == "secrets") {
            report.add(
                "AG205",
                "error",
                "expressions must not reference secrets.*",
                pointer,
            );
            continue;
        }
        if parts.first().is_some_and(|part| part == "params") {
            if parts.len() >= 2 && !scope.param_names.contains(&parts[1]) {
                report.add(
                    "AG203",
                    "error",
                    format!("undeclared param {:?}", parts[1]),
                    pointer,
                );
            }
            continue;
        }
        if parts.first().is_some_and(|part| part == "nodes") && parts.len() >= 2 {
            let target = &parts[1];
            if !scope.nodes.contains_key(target) {
                let child_bound = pointer.contains("/loop/condition")
                    || pointer.contains("/loop/collect/")
                    || pointer.contains("/map/collect/");
                if !child_bound {
                    report.add(
                        if scope.root { "AG203" } else { "AG202" },
                        "error",
                        format!("unknown node {target:?}"),
                        pointer,
                    );
                }
            } else {
                if parts.len() >= 4
                    && parts[2] == "outputs"
                    && !declared_outputs(object(scope.nodes.get(target))).contains(&parts[3])
                {
                    report.add(
                        "AG206",
                        "error",
                        format!("node {target:?} does not declare output {:?}", parts[3]),
                        pointer,
                    );
                } else if target != node_id && !predecessors.contains(target) {
                    report.add(
                        "AG201",
                        "error",
                        format!("node {node_id:?} reads output of non-predecessor {target:?}"),
                        pointer,
                    );
                }
            }
        }
    }
}

fn declared_outputs(node: &serde_json::Map<String, Value>) -> BTreeSet<String> {
    let mut outputs: BTreeSet<String> = object(node.get("outputs")).keys().cloned().collect();
    let kind = node.get("type").and_then(Value::as_str).unwrap_or("task");
    if matches!(kind, "decision" | "gate") {
        outputs.insert("decision".into());
    }
    let block = object(node.get(kind));
    if matches!(kind, "gate" | "loop" | "map") {
        outputs.extend(object(block.get("collect")).keys().cloned());
    }
    if kind == "subgraph" {
        outputs.extend(object(block.get("outputs_from")).keys().cloned());
    }
    outputs
}

fn validate_recursion(document: &Document, report: &mut ValidationReport) {
    let fragments = object(document.get("subgraphs"));
    let mut dependencies: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (name, raw) in fragments {
        for node in object(object(Some(raw)).get("nodes")).values() {
            let node = object(Some(node));
            for kind in ["loop", "map", "subgraph"] {
                if let Some(used) = object(node.get(kind)).get("use").and_then(Value::as_str) {
                    dependencies
                        .entry(name.clone())
                        .or_default()
                        .push(used.into());
                }
            }
        }
    }
    fn visit(
        name: &str,
        dependencies: &BTreeMap<String, Vec<String>>,
        active: &mut Vec<String>,
        done: &mut BTreeSet<String>,
        report: &mut ValidationReport,
    ) {
        if let Some(at) = active.iter().position(|item| item == name) {
            let mut cycle = active[at..].to_vec();
            cycle.push(name.into());
            report.add(
                "AG131",
                "error",
                format!("recursive subgraph reference: {}", cycle.join(" -> ")),
                format!("/subgraphs/{name}"),
            );
            return;
        }
        if done.contains(name) {
            return;
        }
        active.push(name.into());
        for next in dependencies.get(name).into_iter().flatten() {
            visit(next, dependencies, active, done, report);
        }
        active.pop();
        done.insert(name.into());
    }
    let mut done = BTreeSet::new();
    for name in fragments.keys() {
        visit(name, &dependencies, &mut vec![], &mut done, report);
    }
}

#[allow(dead_code)]
fn _root_edges(document: &Document) {
    let _ = graph_effective_edges(document);
}

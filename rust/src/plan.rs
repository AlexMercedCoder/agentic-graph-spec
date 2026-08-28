use std::collections::{BTreeMap, BTreeSet, VecDeque};

use thiserror::Error;

use crate::{Document, EffectiveEdge, GraphPlan, graph_digest, object, strings};

/// Failure while constructing a deterministic graph plan.
#[derive(Debug, Error)]
pub enum PlanError {
    /// The effective graph contains a directed cycle.
    #[error("graph contains a cycle")]
    Cycle,
    /// Canonical graph identity calculation failed.
    #[error(transparent)]
    Digest(#[from] crate::canonical::CanonicalError),
}

/// Combines `depends_on` relationships and explicit edges into a sorted edge set.
pub fn graph_effective_edges(document: &Document) -> Vec<EffectiveEdge> {
    let nodes = object(document.get("nodes"));
    let mut edges = Vec::new();
    let mut seen = BTreeSet::new();
    for (id, raw) in nodes {
        for dependency in strings(raw.as_object().and_then(|node| node.get("depends_on"))) {
            let key = (dependency.clone(), id.clone(), "sequence".to_owned());
            if seen.insert(key.clone()) {
                edges.push(EffectiveEdge {
                    from: key.0,
                    to: key.1,
                    kind: key.2,
                    when: None,
                });
            }
        }
    }
    for raw in document
        .get("edges")
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
    {
        let edge = object(Some(raw));
        let from = edge
            .get("from")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_owned();
        let to = edge
            .get("to")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_owned();
        let kind = edge
            .get("kind")
            .and_then(|v| v.as_str())
            .unwrap_or("sequence")
            .to_owned();
        if seen.insert((from.clone(), to.clone(), kind.clone())) {
            edges.push(EffectiveEdge {
                from,
                to,
                kind,
                when: edge.get("when").and_then(|v| v.as_str()).map(str::to_owned),
            });
        }
    }
    edges.sort_by(|left, right| {
        (&left.from, &left.to, &left.kind).cmp(&(&right.from, &right.to, &right.kind))
    });
    edges
}

/// Computes a deterministic, identifier-tiebroken topological node order.
pub fn topological_order(document: &Document) -> Result<Vec<String>, PlanError> {
    let nodes = object(document.get("nodes"));
    let edges = graph_effective_edges(document);
    let mut incoming: BTreeMap<String, usize> = nodes.keys().map(|id| (id.clone(), 0)).collect();
    let mut outgoing: BTreeMap<String, Vec<String>> =
        nodes.keys().map(|id| (id.clone(), vec![])).collect();
    for edge in &edges {
        if incoming.contains_key(&edge.from) && incoming.contains_key(&edge.to) {
            *incoming.get_mut(&edge.to).expect("known node") += 1;
            outgoing
                .get_mut(&edge.from)
                .expect("known node")
                .push(edge.to.clone());
        }
    }
    for targets in outgoing.values_mut() {
        targets.sort();
    }
    let mut ready: BTreeSet<String> = incoming
        .iter()
        .filter(|(_, count)| **count == 0)
        .map(|(id, _)| id.clone())
        .collect();
    let mut order = Vec::with_capacity(nodes.len());
    while let Some(id) = ready.pop_first() {
        order.push(id.clone());
        for target in outgoing.get(&id).into_iter().flatten() {
            let count = incoming.get_mut(target).expect("known target");
            *count -= 1;
            if *count == 0 {
                ready.insert(target.clone());
            }
        }
    }
    if order.len() != nodes.len() {
        return Err(PlanError::Cycle);
    }
    Ok(order)
}

/// Produces a deterministic, non-executing AGS conformance-level-0 plan.
pub fn plan_graph(document: &Document) -> Result<GraphPlan, PlanError> {
    let nodes = object(document.get("nodes"));
    let edges = graph_effective_edges(document);
    let order = topological_order(document)?;
    let entrypoints = strings(document.get("entrypoints"));
    let mut outgoing: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for edge in &edges {
        outgoing
            .entry(edge.from.clone())
            .or_default()
            .push(edge.to.clone());
    }
    let mut reachable = BTreeSet::new();
    let mut queue: VecDeque<String> = entrypoints.iter().cloned().collect();
    while let Some(id) = queue.pop_front() {
        if reachable.insert(id.clone()) {
            queue.extend(outgoing.get(&id).into_iter().flatten().cloned());
        }
    }
    let unreachable = nodes
        .keys()
        .filter(|id| !reachable.contains(*id))
        .cloned()
        .collect();
    let mut histogram = BTreeMap::new();
    let mut worst_case = 0_u64;
    let mut unsupported = BTreeSet::new();
    for raw in nodes.values() {
        let node = object(Some(raw));
        let tier = object(node.get("intelligence"))
            .get("tier")
            .and_then(|v| v.as_str())
            .unwrap_or("none");
        *histogram.entry(tier.to_owned()).or_insert(0) += 1;
        let mut executions = 1_u64;
        if node.get("type").and_then(|v| v.as_str()) == Some("loop") {
            executions = object(node.get("loop"))
                .get("max_iterations")
                .and_then(|v| v.as_u64())
                .unwrap_or(1);
            unsupported.insert("loop".to_owned());
        }
        if node.get("type").and_then(|v| v.as_str()) == Some("map") {
            executions = object(node.get("map"))
                .get("max_items")
                .and_then(|v| v.as_u64())
                .unwrap_or(1);
            unsupported.insert("map".to_owned());
        }
        if matches!(
            node.get("type").and_then(|v| v.as_str()),
            Some("decision" | "subgraph")
        ) {
            unsupported.insert(
                node.get("type")
                    .and_then(|v| v.as_str())
                    .unwrap()
                    .to_owned(),
            );
        }
        worst_case = worst_case.saturating_add(executions);
    }
    Ok(GraphPlan {
        graph_id: document
            .get("id")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_owned(),
        graph_digest: graph_digest(document)?,
        order,
        entrypoints,
        effective_edges: edges,
        reachable: reachable.into_iter().collect(),
        unreachable,
        tier_histogram: histogram,
        worst_case_node_executions: worst_case,
        executable: false,
        unsupported_features: unsupported.into_iter().collect(),
    })
}

//! Native Rust support for Agentic Graph Specification (AGS) 1.0.
//!
//! The crate parses JSON/YAML graphs, validates structural and semantic rules,
//! computes RFC 8785 identities, parses AGX expressions, and creates deterministic
//! conformance-level-0 plans. It never executes a graph.

#![warn(missing_docs)]

mod agx;
mod canonical;
mod parse;
mod plan;
mod validate;

pub use agx::{AgxCall, AgxError, ParsedExpression, parse_expression};
pub use canonical::{CanonicalError, canonical_json, graph_digest};
pub use parse::{ParseError, load, parse};
pub use plan::{PlanError, graph_effective_edges, plan_graph, topological_order};
pub use validate::{validate, validate_path};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// AGS specification version implemented by this crate.
pub const AGS_VERSION: &str = "1.0";
/// Version of this Rust support library.
pub const SUPPORT_VERSION: &str = "1.0.3";
/// A parsed AGS document represented as a JSON-compatible object.
pub type Document = Map<String, Value>;

/// One machine-readable validation diagnostic.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Finding {
    /// Stable diagnostic code from the AGS validation catalog.
    pub code: String,
    /// Diagnostic severity, either `error` or `warning`.
    pub severity: String,
    /// Human-readable explanation of the diagnostic.
    pub message: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    /// JSON Pointer locating the affected value, when available.
    pub pointer: String,
}

/// The complete result of parsing and validating an AGS document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationReport {
    #[serde(skip_serializing_if = "Option::is_none")]
    /// Parsed document, absent only when loading or parsing failed.
    pub document: Option<Document>,
    /// All errors and warnings in discovery order.
    pub findings: Vec<Finding>,
    /// Findings whose severity is `error`.
    pub errors: Vec<Finding>,
    /// Findings whose severity is `warning`.
    pub warnings: Vec<Finding>,
    /// Whether the document has no validation errors.
    pub ok: bool,
}

impl ValidationReport {
    fn new(document: Document) -> Self {
        Self {
            document: Some(document),
            findings: vec![],
            errors: vec![],
            warnings: vec![],
            ok: true,
        }
    }

    fn add(
        &mut self,
        code: &str,
        severity: &str,
        message: impl Into<String>,
        pointer: impl Into<String>,
    ) {
        let finding = Finding {
            code: code.into(),
            severity: severity.into(),
            message: message.into(),
            pointer: pointer.into(),
        };
        self.findings.push(finding.clone());
        if severity == "error" {
            self.errors.push(finding);
            self.ok = false;
        } else {
            self.warnings.push(finding);
        }
    }
}

/// A normalized dependency or explicitly declared graph edge.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EffectiveEdge {
    /// Source node identifier.
    pub from: String,
    /// Destination node identifier.
    pub to: String,
    /// AGS edge kind.
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    /// Optional AGX condition attached to the edge.
    pub when: Option<String>,
}

/// Deterministic, non-executing conformance-level-0 graph plan.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GraphPlan {
    /// Graph identifier from the source document.
    pub graph_id: String,
    /// RFC 8785/SHA-256 identity of the graph.
    pub graph_digest: String,
    /// Deterministic topological node order.
    pub order: Vec<String>,
    /// Declared graph entrypoints.
    pub entrypoints: Vec<String>,
    /// Normalized dependency and explicit edges.
    pub effective_edges: Vec<EffectiveEdge>,
    /// Nodes reachable from an entrypoint.
    pub reachable: Vec<String>,
    /// Nodes not reachable from any entrypoint.
    pub unreachable: Vec<String>,
    /// Count of nodes by intelligence tier.
    pub tier_histogram: std::collections::BTreeMap<String, usize>,
    /// Conservative upper bound on node executions.
    pub worst_case_node_executions: u64,
    /// Always false because Level 0 plans never execute graphs.
    pub executable: bool,
    /// Features that require a higher conformance execution tier.
    pub unsupported_features: Vec<String>,
}

pub(crate) fn object(value: Option<&Value>) -> &Map<String, Value> {
    value.and_then(Value::as_object).unwrap_or_else(|| {
        static EMPTY: std::sync::LazyLock<Map<String, Value>> = std::sync::LazyLock::new(Map::new);
        &EMPTY
    })
}

pub(crate) fn strings(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect()
}

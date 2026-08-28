use base64::{Engine as _, engine::general_purpose::STANDARD};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::Document;

/// Failure while producing canonical JSON.
#[derive(Debug, Error)]
pub enum CanonicalError {
    /// The value could not be serialized.
    #[error("canonical JSON error: {0}")]
    Serialize(#[from] serde_json::Error),
}

/// Serializes a value using RFC 8785 JSON Canonicalization Scheme rules.
pub fn canonical_json(value: &impl serde::Serialize) -> Result<Vec<u8>, CanonicalError> {
    Ok(serde_jcs::to_vec(value)?)
}

/// Computes the AGS `sha256-<base64>` identity of a graph document.
pub fn graph_digest(document: &Document) -> Result<String, CanonicalError> {
    let digest = Sha256::digest(canonical_json(document)?);
    Ok(format!("sha256-{}", STANDARD.encode(digest)))
}

use std::{fs, path::Path};

use serde::{
    Deserialize, Deserializer,
    de::{MapAccess, SeqAccess, Visitor},
};
use serde_json::{Map, Number, Value};
use thiserror::Error;

use crate::Document;

/// AGS parsing failure with a stable diagnostic code.
#[derive(Debug, Error)]
#[error("{message}")]
pub struct ParseError {
    /// `AG001` for general parse failures or `AG005` for duplicate keys.
    pub code: &'static str,
    /// Human-readable parsing failure.
    pub message: String,
}

/// Parses a JSON or YAML AGS document with duplicate-key rejection.
///
/// `format` is matched case-insensitively; `json` selects JSON and all other
/// values select YAML.
pub fn parse(input: &str, format: &str) -> Result<Document, ParseError> {
    if input.trim().is_empty() {
        return Err(ParseError {
            code: "AG001",
            message: "parse error: empty document".into(),
        });
    }
    let value: Value = if format.eq_ignore_ascii_case("json") {
        serde_json::from_str(input).map_err(|error| ParseError {
            code: "AG001",
            message: format!("parse error: {error}"),
        })?
    } else {
        serde_yaml_ng::from_str::<UniqueValue>(input)
            .map(|value| value.0)
            .map_err(|error| {
                let text = error.to_string();
                let code = if text.to_lowercase().contains("duplicate") {
                    "AG005"
                } else {
                    "AG001"
                };
                ParseError {
                    code,
                    message: format!("parse error: {text}"),
                }
            })?
    };
    value.as_object().cloned().ok_or(ParseError {
        code: "AG001",
        message: "document root must be an object".into(),
    })
}

struct UniqueValue(Value);

impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct ValueVisitor;
        impl<'de> Visitor<'de> for ValueVisitor {
            type Value = UniqueValue;
            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("a JSON-compatible YAML value")
            }
            fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Bool(value)))
            }
            fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(value.into())))
            }
            fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(value.into())))
            }
            fn visit_f64<E: serde::de::Error>(self, value: f64) -> Result<Self::Value, E> {
                Number::from_f64(value)
                    .map(Value::Number)
                    .map(UniqueValue)
                    .ok_or_else(|| E::custom("non-finite number"))
            }
            fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(value.into())))
            }
            fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(value)))
            }
            fn visit_none<E>(self) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_unit<E>(self) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut sequence: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = vec![];
                while let Some(value) = sequence.next_element::<UniqueValue>()? {
                    values.push(value.0);
                }
                Ok(UniqueValue(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut mapping: A) -> Result<Self::Value, A::Error> {
                let mut values = Map::new();
                while let Some((key, value)) = mapping.next_entry::<String, UniqueValue>()? {
                    if values.contains_key(&key) {
                        return Err(serde::de::Error::custom(format!("duplicate key {key:?}")));
                    }
                    values.insert(key, value.0);
                }
                Ok(UniqueValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(ValueVisitor)
    }
}

/// Loads an AGS document, selecting JSON for `.json` paths and YAML otherwise.
pub fn load(path: impl AsRef<Path>) -> Result<Document, ParseError> {
    let path = path.as_ref();
    let input = fs::read_to_string(path).map_err(|error| ParseError {
        code: "AG001",
        message: error.to_string(),
    })?;
    let format = if path
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("json"))
    {
        "json"
    } else {
        "yaml"
    };
    parse(&input, format)
}

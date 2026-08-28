import { createHash } from "node:crypto";

import canonicalize from "canonicalize";

import type { JsonObject, JsonValue } from "./types.js";

export function canonicalJson(value: JsonValue): Uint8Array {
  const encoded = canonicalize(value);
  if (encoded === undefined) {
    throw new TypeError("value is not representable as canonical JSON");
  }
  return new TextEncoder().encode(encoded);
}

export function graphDigest(document: JsonObject): string {
  const digest = createHash("sha256").update(canonicalJson(document)).digest("base64");
  return `sha256-${digest}`;
}

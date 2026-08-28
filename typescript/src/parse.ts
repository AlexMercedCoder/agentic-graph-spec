import { readFile } from "node:fs/promises";
import { extname } from "node:path";

import { parseDocument as parseYamlDocument } from "yaml";

import type { Finding, JsonObject, JsonValue } from "./types.js";

export class ParseError extends Error {
  constructor(
    message: string,
    readonly code: "AG001" | "AG005" = "AG001",
  ) {
    super(message);
    this.name = "ParseError";
  }
}

function asJsonValue(value: unknown): JsonValue {
  if (
    value === null ||
    typeof value === "boolean" ||
    typeof value === "number" ||
    typeof value === "string"
  ) {
    return value;
  }
  if (Array.isArray(value)) return value.map(asJsonValue);
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, asJsonValue(child)]),
    );
  }
  throw new ParseError(`document contains a non-JSON value of type ${typeof value}`);
}

export function parseGraph(text: string, format: "json" | "yaml" = "yaml"): JsonObject {
  let value: unknown;
  if (format === "json") {
    try {
      value = JSON.parse(text);
    } catch (error) {
      throw new ParseError(`parse error: ${(error as Error).message}`);
    }
  } else {
    const parsed = parseYamlDocument(text, {
      schema: "core",
      uniqueKeys: true,
      prettyErrors: true,
    });
    if (parsed.errors.length > 0) {
      const message = parsed.errors.map((error) => error.message).join("; ");
      const duplicate = message.toLowerCase().includes("unique");
      throw new ParseError(`parse error: ${message}`, duplicate ? "AG005" : "AG001");
    }
    value = parsed.toJS({ maxAliasCount: 100 });
  }
  const json = asJsonValue(value);
  if (json === null || Array.isArray(json) || typeof json !== "object") {
    throw new ParseError("document root must be an object");
  }
  return json;
}

export async function loadGraph(path: string): Promise<JsonObject> {
  const text = await readFile(path, "utf8");
  return parseGraph(text, extname(path).toLowerCase() === ".json" ? "json" : "yaml");
}

export function parseFinding(error: unknown): Finding {
  const parsed = error instanceof ParseError ? error : new ParseError(String(error));
  return { code: parsed.code, severity: "error", message: parsed.message, pointer: "" };
}

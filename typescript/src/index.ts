export const AGS_VERSION = "1.0";
export const SUPPORT_VERSION = "1.0.4";

import { loadGraph as loadGraphDocument } from "./parse.js";
import type { ValidationReport } from "./types.js";
import { validateGraph as validateGraphDocument } from "./validate.js";

/** Load and validate one AGS document, matching the Python support package's convenience API. */
export async function validatePath(path: string): Promise<ValidationReport> {
  return validateGraphDocument(await loadGraphDocument(path));
}

export { canonicalJson, graphDigest } from "./canonical.js";
export { AGX_FUNCTIONS, AgxSyntaxError, parseExpression } from "./agx.js";
export { loadGraph, parseGraph, ParseError } from "./parse.js";
export { graphEffectiveEdges, planGraph, topologicalOrder } from "./plan.js";
export { graphSchema, validateGraph, validateValue } from "./validate.js";
export type {
  EffectiveEdge,
  Finding,
  GraphPlan,
  JsonObject,
  JsonPrimitive,
  JsonValue,
  Severity,
  ValidationReport,
} from "./types.js";

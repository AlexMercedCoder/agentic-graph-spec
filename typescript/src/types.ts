export type JsonPrimitive = null | boolean | number | string;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export type Severity = "error" | "warning";

export interface Finding {
  code: string;
  severity: Severity;
  message: string;
  pointer: string;
}

export interface ValidationReport {
  document?: JsonObject;
  findings: Finding[];
  errors: Finding[];
  warnings: Finding[];
  ok: boolean;
}

export interface EffectiveEdge {
  from: string;
  to: string;
  kind: string;
  when?: string;
}

export interface GraphPlan {
  graphId: string;
  graphDigest: string;
  order: string[];
  entrypoints: string[];
  effectiveEdges: EffectiveEdge[];
  reachable: string[];
  unreachable: string[];
  tierHistogram: Record<string, number>;
  worstCaseNodeExecutions: number;
  executable: false;
  unsupportedFeatures: string[];
}

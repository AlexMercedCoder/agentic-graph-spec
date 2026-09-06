# WebMCP integration

AGS already supports WebMCP through node requirements. No new normative field is needed: a task
declares the portable capability `webmcp` (and optionally `webmcp/read` or `webmcp/call`), while the
harness resolves that capability against a live page registry.

## Planning rules

- A planner SHOULD declare `webmcp` only when the task actually needs browser-native site tools.
- Tool names invented by a model MUST NOT be treated as available. The harness resolves aliases
  against the live registry and rejects undeclared or missing tools before starting the node.
- A graph artifact SHOULD NOT embed cookies, access tokens, browser-profile paths, or other
  credentials. Exact allowed origins are host policy, not graph authority.
- A node that invokes a live tool SHOULD pin the registry revision for that attempt. A changed
  revision causes rediscovery and replanning, not execution against stale metadata.
- Read-only and mutating calls pass through the node's declared permissions, the active OAP
  profile, host policy, and AAIS approval where required.

## Execution and recovery

The event stream SHOULD expose navigation, discovery, approval waiting, invocation, completion,
and failure without revealing private model reasoning. Audit records SHOULD include the graph and
node identifiers, origin, URL, tool, revision, attempt, decision reference, timing, and redacted
result summary.

If a required WebMCP capability is unavailable, the node fails as an unmet capability before model
execution. A harness MAY route the node to another compatible runtime or use the graph's existing
retry/fallback policy. It MUST NOT silently substitute an unrelated tool.

See [`examples/webmcp-research.agraph.yaml`](../examples/webmcp-research.agraph.yaml).

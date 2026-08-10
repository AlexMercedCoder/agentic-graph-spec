# AGX — the Agentic Graph expression language

AGX is the small language AGS uses for conditions, bindings and machine-checkable criteria. It is
deliberately tiny: **pure, total, side-effect-free, and replayable**. This document is the reference;
[SPEC.md §16](../SPEC.md#16-agx-the-expression-language) is the normative summary.

## 1. Two syntactic positions

### Expression position

The *entire string* is one expression. No wrapper, no interpolation.

```yaml
when: nodes.review.outputs.verdict == "approved"
expr: len(self.outputs.findings) == 0
over: nodes.detect_changes.outputs.modules
from: nodes.design.outputs.design_doc
```

Fields in expression position: `edge.when`, `node.when`, `human[].when`,
`fallback[].when`, `decision.branches[].when`, `loop.condition`, `map.over`,
`inputs.*.from`, `outputs.*.from`, `loop.collect.*`, `map.collect.*`,
`subgraph.params.*`, `subgraph.outputs_from.*`, `gate.present[]`,
`criterion.expr`, `criterion.target`, `criterion.inputs[]`.

Using `${{ }}` here is validation error **AG211**.

### Template position

Text with `${{ ... }}` interpolation. Everything outside the braces is literal.

```yaml
prompt: |
  Approve release ${{ params.target_version }}?
  Integration suite: ${{ nodes.run_suite.outputs.summary }}
```

Fields in template position: `node.instructions`, `inputs.*.template`, `gate.prompt`,
`decision.question`, `human[].prompt`, `escalation.message`, `criterion.rubric`,
`criterion.prompt`.

Interpolated values are stringified: scalars render directly, `null` renders as the empty string,
and objects and arrays render as compact JSON.

## 2. Scopes

An expression sees exactly the namespaces its position makes available.

| Namespace | Where | Contents |
| --- | --- | --- |
| `graph` | everywhere | `graph.id`, `graph.title`, `graph.objective`, `graph.version`, `graph.description` |
| `params` | its own graph or fragment | Declared parameters. Inside a fragment with its own `params`, those shadow the graph's. |
| `context` | its own graph | Declared context entries. Immutable for the whole run. |
| `attachments` | its own graph | Declared attachments, by name. |
| `nodes.<id>` | same scope only | `.status`, `.outputs.<name>`, `.attempts`, `.duration_seconds`, `.decision` |
| `self` | within a node | `self.id`, `self.attempt`, `self.inputs.<name>`, `self.outputs.<name>` |
| `nodes.self` | within a node | Alias of `self`. Useful when a template reads more naturally that way. |
| `loop` | inside a loop body | `loop.index` (0-based), `loop.iteration` (1-based), `loop.previous.<name>` |
| *`map.as`* | inside a map body | The current element, under whatever name `map.as` gives it. |
| *`map.index_as`* | inside a map body | The 0-based element index. Defaults to `index`. |
| `outputs` | graph-level `outputs`/`success`, and `subgraph.outputs_from` | Bound graph outputs (or, in `outputs_from`, the child's). |
| `env` | within a node | Only names listed in that node's `requirements.environment`. |
| `secrets` | **nowhere** | Referencing it is **AG205**. |

Three scope rules matter in practice:

- **Fragments are sealed.** A node inside a loop, map or subgraph body cannot reference
  `nodes.*` outside the fragment (**AG202**). Everything a fragment needs arrives through
  `params`. This is what makes fragments relocatable.
- **`self.outputs` is only populated after the node's loop finishes.** It is available in
  `success` criteria and in `human` checkpoints at `after_outputs` or later — not in `inputs`.
- **Reading forward is a load-time error.** `nodes.X.outputs.*` is only legal if `X` is a
  transitive predecessor of the referencing node in the effective edge set (**AG201**). On an
  edge's `when`, the edge's own source counts as available.

## 3. Grammar

```
expression  := or_expr
or_expr     := and_expr   ( ("||" | "or")  and_expr )*
and_expr    := in_expr    ( ("&&" | "and") in_expr )*
in_expr     := eq_expr    ( "in" eq_expr )*
eq_expr     := cmp_expr   ( ("==" | "!=") cmp_expr )*
cmp_expr    := add_expr   ( ("<" | "<=" | ">" | ">=") add_expr )*
add_expr    := mul_expr   ( ("+" | "-") mul_expr )*
mul_expr    := unary      ( ("*" | "/" | "%") unary )*
unary       := ("!" | "not" | "-") unary | primary
primary     := literal
             | "(" expression ")"
             | "[" [ expression ( "," expression )* ] "]"
             | function "(" [ expression ( "," expression )* ] ")"
             | reference
reference   := IDENT ( "." IDENT )*
literal     := NUMBER | STRING | "true" | "false" | "null"
```

Strings use single or double quotes with backslash escapes. Identifiers match
`[A-Za-z_][A-Za-z0-9_]*`.

There is no assignment, no user-defined function, no lambda, no loop, no I/O, and nothing
time-dependent. `now()` deliberately does not exist: an expression must produce the same value when
replayed from a run record.

## 4. Types and coercion

AGX values are JSON values: string, number, boolean, null, array, object.

**Comparison is strictly typed.** Comparing a string to a number is an *evaluation error*, not
`false`. This is intentional — silent type coercion in a guard expression routes a graph down the
wrong branch and leaves no trace.

| Operation | Rule |
| --- | --- |
| `==`, `!=` | Deep equality. Different types are never equal, and comparing them is not an error. |
| `<`, `<=`, `>`, `>=` | Numbers with numbers, or strings with strings (lexicographic). Anything else is an error. |
| `+` | Numbers, or string concatenation, or array concatenation. Mixed operands are an error. |
| `-`, `*`, `/`, `%` | Numbers only. Division or modulo by zero is an error. |
| `&&`, `\|\|`, `!` | Booleans only. There is no truthiness; use `len(x) > 0` rather than `x`. |
| `in` | `needle in haystack` where haystack is an array (membership), a string (substring), or an object (key presence). |

Missing values: reading an undeclared name is a **load-time** error (AG203/AG206). Reading a
declared name whose value is absent at run time yields `null`; use `default(x, fallback)` to
handle it.

## 5. Functions

All functions are pure and total. Wrong arity or wrong argument types is **AG204** at load time
where statically detectable, and an evaluation error at run time otherwise.

| Function | Signature | Notes |
| --- | --- | --- |
| `len(x)` | array/string/object → integer | Length, character count, or key count. |
| `count(x)` | array → integer | Alias of `len` for arrays; reads better in criteria. |
| `contains(a, b)` | (string\|array\|object, any) → boolean | Substring, membership, or key presence. |
| `startswith(s, p)` | (string, string) → boolean | |
| `endswith(s, p)` | (string, string) → boolean | |
| `lower(s)` / `upper(s)` / `trim(s)` | string → string | |
| `matches(s, pattern)` | (string, string) → boolean | Unanchored regular expression. |
| `split(s, sep)` | (string, string) → array | |
| `join(list, sep)` | (array, string) → string | Elements are stringified. |
| `int(x)` / `float(x)` / `bool(x)` / `str(x)` | any → scalar | Explicit conversion. Failure is an evaluation error. |
| `json(s)` | string → any | Parse a JSON string. |
| `get(obj, path, default?)` | (object, string, any) → any | Dotted-path lookup that does not error on a missing key. |
| `default(x, fallback)` | (any, any) → any | `fallback` when `x` is `null` or absent. |
| `any(list)` / `all(list)` | array of boolean → boolean | `all([])` is `true`; `any([])` is `false`. |
| `succeeded(id)` / `failed(id)` / `skipped(id)` | string → boolean | State of a node in the current scope. |
| `output(id, name)` | (string, string) → any | Dynamic form of `nodes.<id>.outputs.<name>`. Subject to the same predecessor rule. |

Implementations MUST NOT add functions to this list under a bare name. A harness-specific helper
belongs behind an `x-` extension and makes the graph non-portable.

## 6. Evaluation errors

An evaluation error is: an unknown name at run time, wrong argument types, a type-mismatched
comparison, division by zero, or a failed conversion.

`policy.on_expression_error` decides what happens:

- `fail` (default) — the error is run-fatal. Preferred, because a guard that silently evaluates to
  `false` looks exactly like a branch that was deliberately not taken.
- `false` — the expression yields `false`, diagnostic `RT062` is recorded with the offending
  expression, and the run continues.

## 7. Worked examples

```yaml
# Route on a decision node's label.
when: nodes.triage.outputs.decision == "product_bug"

# Route on a subgraph's structured output.
when: len(nodes.link_audit.outputs.broken_links) > 0

# Two conditions.
when: nodes.scan.outputs.severity == "high" && params.environment == "production"

# Membership.
when: "auth" in nodes.detect_changes.outputs.modules

# Guard a human review to expensive changes only.
when: nodes.self.outputs.estimated_impact > 0.5

# A criterion over a node's own output.
expr: self.outputs.coverage_percent >= 85

# A criterion over structured output.
expr: all([len(self.outputs.findings) == 0, self.outputs.exit_code == 0])

# Tolerate an output that may not exist because a branch was skipped.
last_change: default(nodes.apply_fix.outputs.summary, "no fix applied in the final iteration")

# Inside a loop body: do something different on the first pass.
when: loop.iteration > 1

# Inside a map body: name the item.
from: page

# Template interpolation.
prompt: "Publish ${{ params.target_version }} to ${{ params.package_index }}?"
```

## 8. Implementing AGX

The reference implementation is
[`tools/validate_agraph.py`](../tools/validate_agraph.py) (`AgxParser`) — a ~150-line recursive
descent parser with one production per precedence level. It validates syntax, checks function arity,
and collects references for scope and dataflow analysis. Add an evaluator and you have the runtime
half.

Two implementation notes worth stating:

- **Do not implement AGX by calling your host language's `eval`.** Graph documents are untrusted
  input ([SPEC.md §22](../SPEC.md#22-security-considerations)); an expression must never be able to
  reach the host runtime.
- **Validate expressions at load time, not first use.** A typo in a guard on the eighth node should
  fail before the first node spends a token. All of AG201–AG211 are statically decidable.
